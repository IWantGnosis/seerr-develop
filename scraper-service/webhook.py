from flask import Flask, request, jsonify, send_from_directory
import threading
import time
import re
import os
import json
import logging
import sys
import collections
from datetime import datetime
import urllib.request
import scrapers.scraper as scraper
import rename_clean_dots

# Silence GET /api/downloads and /api/logs terminal spam
logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)

jobs = {}
log_buffer = collections.deque(maxlen=300)

class LogInterceptor:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, message):
        self.original_stdout.write(message)
        clean = message.strip()
        if not clean:
            return

        # Suppress carriage-return progress bars (\r[###...]) from spamming the web log stream
        # (The UI card already renders its own dedicated real-time progress bar)
        if message.startswith("\r") or ("[" in clean and "%" in clean and ("MB/s" in clean or "ETA" in clean or "downloading" in clean)):
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        log_buffer.append(f"[{timestamp}] {clean}")

    def flush(self):
        self.original_stdout.flush()

sys.stdout = LogInterceptor(sys.stdout)

SEERR_API_KEY = "MTc5MTAzMzU5ODIwM2ZkZDA3YmM5LTQ2OTctNDYyMy1iZGZmLTgyZGE5NzhiOWE2MA=="
SEERR_API_URL = os.environ.get("SEERR_API_URL", "http://seerr:5055/api/v1")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "3b9832f7a92f4db9ad9655a021c38fed")
JELLYFIN_TASK_ID = "32b3cf16bac4a2b0068fb5e08d48d20f"
INDIAN_LANGUAGES = {"hi", "ta", "te", "ml", "kn", "pa", "bn", "mr", "gu", "ur"}


def trigger_jellyfin_autofix_pipeline(delay_sec=10):
    """
    Automated post-download pipeline:
    1. Triggers Jellyfin to scan library for the newly downloaded file.
    2. Waits for Jellyfin to resolve TMDb metadata.
    3. Triggers AutoFix scheduled task to cleanly rename the file to Title (Year).ext.
    """
    candidate_urls = [
        os.environ.get("JELLYFIN_URL", "http://jellyfin:8096"),
        "http://192.168.29.75:8096",
        "http://localhost:8096",
        "http://127.0.0.1:8096",
    ]
    unique_urls = list(dict.fromkeys(candidate_urls))
    headers = {
        "Authorization": f'MediaBrowser Client="SeerrScraper", Device="Server", DeviceId="seerr-scraper", Version="1.0.0", Token="{JELLYFIN_API_KEY}"',
        "Content-Type": "application/json",
    }

    # Step 1: Refresh Jellyfin library so it scans the new movie file
    for base in unique_urls:
        try:
            req = urllib.request.Request(f"{base}/Library/Refresh", data=b"", headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=4):
                print(f"[Pipeline] Successfully requested Jellyfin library scan via {base}")
                break
        except Exception:
            continue

    # Step 2: Give Jellyfin a few seconds to discover and fetch TMDb metadata
    print(f"[Pipeline] Waiting {delay_sec}s for Jellyfin to index and fetch TMDb metadata...")
    time.sleep(delay_sec)

    # Step 3: Trigger AutoFix scheduled task to rename the movie in-place using confirmed metadata
    for base in unique_urls:
        try:
            req = urllib.request.Request(f"{base}/ScheduledTasks/Running/{JELLYFIN_TASK_ID}", data=b"", headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5):
                print(f"[Pipeline] Triggered AutoFix clean renaming task via {base}!")
                break
        except Exception:
            continue



# Media Library Destination Directories
HOLLYWOOD_DIR = os.environ.get("HOLLYWOOD_FOLDER", "/media/myfiles/Hollywood Movies")
BOLLYWOOD_DIR = os.environ.get("BOLLYWOOD_FOLDER", "/media/myfiles/Bollywood Movies")


def get_destination_folder(is_indian):
    target = BOLLYWOOD_DIR if is_indian else HOLLYWOOD_DIR
    if not os.path.exists(target):
        try:
            os.makedirs(target, exist_ok=True)
        except Exception:
            # Fallback for Windows desktop local testing
            base = os.environ.get("DOWNLOAD_FOLDER", os.path.join(os.path.expanduser("~"), "Downloads"))
            target = os.path.join(base, "Bollywood Movies" if is_indian else "Hollywood Movies")
            os.makedirs(target, exist_ok=True)
    return target


def check_is_indian_movie(tmdb_id):
    """
    Detects if a movie is an Indian production by querying Seerr / TMDB metadata:
    1. Checks if 'IN' is present in productionCountries
    2. Checks if originalLanguage is one of the Indian regional languages
    """
    if not tmdb_id or tmdb_id == "unknown":
        return False

    candidate_urls = [
        SEERR_API_URL,
        "http://seerr:5055/api/v1",
        "http://localhost:5055/api/v1",
        "http://192.168.29.75:5055/api/v1",
    ]
    # Remove duplicates while preserving order
    unique_urls = list(dict.fromkeys(candidate_urls))

    for base_url in unique_urls:
        try:
            req = urllib.request.Request(
                f"{base_url}/movie/{tmdb_id}",
                headers={"X-Api-Key": SEERR_API_KEY}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                countries = [c.get("iso_3166_1", "").upper() for c in data.get("productionCountries", [])]
                if "IN" in countries:
                    print(f"[Detector] Movie {tmdb_id} has productionCountry 'IN' -> Indian Production")
                    return True
                lang = (data.get("originalLanguage") or "").lower()
                if lang in INDIAN_LANGUAGES:
                    print(f"[Detector] Movie {tmdb_id} has Indian originalLanguage '{lang}' -> Indian Production")
                    return True
                return False
        except Exception:
            continue

    print(f"[Detector] Note: Could not query Seerr API for movie {tmdb_id} across endpoints, defaulting to International")
    return False


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response



job_cancel_events = {}
job_drivers = {}

# ---------------------------------------------------------
# Concurrency & Download Queue System
# ---------------------------------------------------------
MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "1"))
download_queue = collections.deque()
active_jobs = set()
queue_lock = threading.RLock()


def update_queued_job_positions():
    """
    Updates the display speed/status for all jobs currently waiting in the queue.
    """
    with queue_lock:
        for idx, q_params in enumerate(download_queue, start=1):
            jid = q_params["job_id"]
            if jid in jobs and jobs[jid].get("status") == "QUEUED":
                jobs[jid]["speed"] = f"Waiting in queue (Position #{idx})"


def process_next_in_queue():
    """
    Pulls waiting jobs from download_queue until active_jobs reaches MAX_CONCURRENT_DOWNLOADS.
    """
    with queue_lock:
        while len(active_jobs) < MAX_CONCURRENT_DOWNLOADS and download_queue:
            next_job_params = download_queue.popleft()
            next_id = next_job_params["job_id"]

            # Skip cancelled, failed, or completed jobs
            if next_id not in jobs or jobs[next_id].get("status") in ("CANCELLED", "FAILED", "COMPLETED"):
                print(f"[Queue] Skipping inactive job {next_id} from queue.")
                continue

            active_jobs.add(next_id)
            jobs[next_id]["status"] = "SEARCHING"
            jobs[next_id]["speed"] = "0 MB/s"
            title = jobs[next_id].get("title", next_id)
            print(f"[Queue] Dequeued '{title}' (ID: {next_id}). Starting download! (Active: {len(active_jobs)}/{MAX_CONCURRENT_DOWNLOADS})")

            thread = threading.Thread(
                target=run_scraper_job,
                kwargs=next_job_params,
                daemon=True,
            )
            thread.start()

        update_queued_job_positions()


def enqueue_or_start_job(job_params):
    """
    If active_jobs < MAX_CONCURRENT_DOWNLOADS, starts immediately.
    Otherwise, marks status as 'QUEUED' and appends to download_queue.
    """
    job_id = job_params["job_id"]
    with queue_lock:
        if len(active_jobs) < MAX_CONCURRENT_DOWNLOADS:
            active_jobs.add(job_id)
            jobs[job_id]["status"] = "SEARCHING"
            jobs[job_id]["speed"] = "0 MB/s"
            title = jobs[job_id].get("title", job_id)
            print(f"[Queue] Slot available ({len(active_jobs)}/{MAX_CONCURRENT_DOWNLOADS}). Starting '{title}' immediately.")
            thread = threading.Thread(
                target=run_scraper_job,
                kwargs=job_params,
                daemon=True,
            )
            thread.start()
        else:
            jobs[job_id]["status"] = "QUEUED"
            download_queue.append(job_params)
            position = len(download_queue)
            jobs[job_id]["speed"] = f"Waiting in queue (Position #{position})"
            title = jobs[job_id].get("title", job_id)
            print(f"[Queue] Limit ({MAX_CONCURRENT_DOWNLOADS}) reached. '{title}' queued at position #{position}.")



def mark_seerr_media_available(media_id=None, tmdb_id=None, is_4k=False):
    """
    Directly marks the movie as AVAILABLE in Seerr, immediately clearing the
    pending request state without waiting for a scheduled Jellyfin sync.
    """
    candidate_urls = [
        SEERR_API_URL,
        "http://seerr:5055/api/v1",
        "http://localhost:5055/api/v1",
        "http://192.168.29.75:5055/api/v1",
    ]
    unique_urls = list(dict.fromkeys(candidate_urls))

    # 1. Update directly via dedicated TMDb ID endpoint (most reliable)
    if tmdb_id and tmdb_id != "unknown":
        for base in unique_urls:
            try:
                body = json.dumps({"is4k": is_4k}).encode("utf-8")
                req = urllib.request.Request(
                    f"{base}/media/by-tmdb/{tmdb_id}/available",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Api-Key": SEERR_API_KEY
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    print(f"[Notifier] Successfully auto-synced Seerr movie (TMDb {tmdb_id}) to AVAILABLE!")
                    return True
            except Exception:
                continue

    # 2. Update directly via internal media_id if available
    if media_id:
        for base in unique_urls:
            try:
                body = json.dumps({"is4k": is_4k}).encode("utf-8")
                req = urllib.request.Request(
                    f"{base}/media/{media_id}/available",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Api-Key": SEERR_API_KEY
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    print(f"[Notifier] Successfully updated Seerr media {media_id} to AVAILABLE!")
                    return True
            except Exception:
                continue

    # 3. Fallback: Query movie by TMDb ID to find internal mediaId
    if tmdb_id and tmdb_id != "unknown":
        for base in unique_urls:
            try:
                req = urllib.request.Request(
                    f"{base}/movie/{tmdb_id}",
                    headers={"X-Api-Key": SEERR_API_KEY}
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    m = data.get("mediaInfo") or data.get("media")
                    if m and m.get("id"):
                        mid = m.get("id")
                        body = json.dumps({"is4k": is_4k}).encode("utf-8")
                        req2 = urllib.request.Request(
                            f"{base}/media/{mid}/available",
                            data=body,
                            headers={
                                "Content-Type": "application/json",
                                "X-Api-Key": SEERR_API_KEY
                            },
                            method="POST"
                        )
                        with urllib.request.urlopen(req2, timeout=4) as resp2:
                            print(f"[Notifier] Successfully updated Seerr media {mid} (TMDb {tmdb_id}) to AVAILABLE!")
                            return True
            except Exception:
                continue

    print(f"[Notifier] Note: Could not auto-sync availability for media {media_id} (TMDb {tmdb_id}).")
    return False


def run_scraper_job(job_id, movie_title, tmdb_id, poster_path, preferred_quality="1080p", is_indian=None, download_folder=None, media_id=None, is_4k=False):
    cancel_event = threading.Event()
    job_cancel_events[job_id] = cancel_event

    def on_driver(driver):
        job_drivers[job_id] = driver

    try:
        def update_progress(percent, speed_str, status):
            if job_id in jobs:
                if cancel_event.is_set():
                    return
                jobs[job_id]["progress"] = round(percent, 1)
                jobs[job_id]["speed"] = speed_str
                jobs[job_id]["status"] = status
                if status == "COMPLETED":
                    jobs[job_id]["completedAt"] = "Just now"
                    # 1. Automatically run dot-to-space rename cleanup on the download folder
                    if download_folder and os.path.exists(download_folder):
                        try:
                            rename_clean_dots.rename_media_in_dir(download_folder)
                        except Exception as re_err:
                            print(f"[Cleaner] Post-download clean error: {re_err}")

                    # 2. Mark media as AVAILABLE in Seerr
                    threading.Thread(
                        target=mark_seerr_media_available,
                        args=(media_id, tmdb_id, is_4k),
                        daemon=True
                    ).start()

                    # 3. Automatically trigger Jellyfin library scan + AutoFix in-place renaming
                    threading.Thread(
                        target=trigger_jellyfin_autofix_pipeline,
                        daemon=True
                    ).start()


        scraper.process_movie(
            movie_title,
            progress_callback=update_progress,
            auto_select=True,
            preferred_quality=preferred_quality,
            headless=True,
            is_indian=is_indian,
            download_folder=download_folder,
            cancel_event=cancel_event,
            on_driver_created=on_driver,
            tmdb_id=tmdb_id,
        )

    except (KeyboardInterrupt, Exception) as e:
        if cancel_event.is_set():
            print(f"[Scraper] Job {job_id} was successfully cancelled.")
            if job_id in jobs:
                jobs[job_id]["status"] = "CANCELLED"
                jobs[job_id]["speed"] = "0 MB/s"
        else:
            err_str = str(e)
            if "Stacktrace:" in err_str:
                err_str = err_str.split("Stacktrace:")[0].strip()
            if "Message:" in err_str:
                err_str = err_str.split("Message:")[1].strip()
            if "DevToolsActivePort" in err_str:
                err_str = "Chromium session failed to start (DevToolsActivePort). The 2GB shared memory update resolves this."
            print(f"Scraper error: {err_str}")
            if job_id in jobs:
                jobs[job_id]["status"] = "FAILED"
                jobs[job_id]["error"] = err_str
    finally:
        driver = job_drivers.pop(job_id, None)
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        job_cancel_events.pop(job_id, None)

        with queue_lock:
            active_jobs.discard(job_id)
            process_next_in_queue()


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    media = data.get("media")

    if not media:
        return jsonify({"status": "ignored"}), 200

    movie_title = data.get("subject", "Unknown Movie")
    tmdb_id = media.get("tmdbId") or "unknown"
    media_id = media.get("id")
    image = data.get("image", "")

    year_match = re.search(r"\((\d{4})\)", movie_title)
    year = int(year_match.group(1)) if year_match else 2024
    clean_title = re.sub(r"\s*\(\d{4}\)", "", movie_title)

    poster_path = (
        f"https://image.tmdb.org/t/p/w342{image}"
        if image.startswith("/")
        else (image or "https://image.tmdb.org/t/p/w342/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg")
    )

    job_id = str(tmdb_id)

    # Check if request specifies 4K
    is_4k = bool(data.get("request", {}).get("is4k") or media.get("status4k") in (2, "2", "AVAILABLE", "PROCESSING"))
    preferred_quality = "2160p" if is_4k else "1080p"

    # Detect if movie is Indian production or Hollywood
    is_indian = check_is_indian_movie(tmdb_id)
    site_source = "MoviesLeech (Bollywood)" if is_indian else "MoviesMod (Hollywood)"
    dest_folder = get_destination_folder(is_indian)

    jobs[job_id] = {
        "id": job_id,
        "title": clean_title,
        "year": year,
        "posterPath": poster_path,
        "quality": preferred_quality,
        "status": "QUEUED",
        "progress": 0,
        "speed": "Waiting in queue",
        "source": site_source,
        "destination": dest_folder,
        "startedAt": "Just now",
    }

    job_params = {
        "job_id": job_id,
        "movie_title": movie_title,
        "tmdb_id": tmdb_id,
        "poster_path": poster_path,
        "preferred_quality": preferred_quality,
        "is_indian": is_indian,
        "download_folder": dest_folder,
        "media_id": media_id,
        "is_4k": is_4k,
    }

    enqueue_or_start_job(job_params)

    return jsonify({
        "status": "received",
        "job_id": job_id,
        "quality": preferred_quality,
        "source": site_source,
        "destination": dest_folder
    }), 200


@app.route("/api/downloads", methods=["GET"])
def get_downloads():
    # Auto-prune completed/cancelled jobs if more than 5 exist to keep history clean
    finished = [jid for jid, j in jobs.items() if j.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]]
    if len(finished) > 5:
        for old_id in finished[:-5]:
            del jobs[old_id]
    return jsonify(list(jobs.values()))


@app.route("/api/downloads/<job_id>/cancel", methods=["POST", "OPTIONS"])
def cancel_job(job_id):
    if request.method == "OPTIONS":
        return "", 200

    if job_id in jobs:
        with queue_lock:
            for item in list(download_queue):
                if item.get("job_id") == job_id:
                    download_queue.remove(item)
            active_jobs.discard(job_id)
            update_queued_job_positions()
            process_next_in_queue()

        # Signal cancellation
        event = job_cancel_events.get(job_id)
        if event:
            event.set()

        # Terminate active browser process immediately
        driver = job_drivers.get(job_id)
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

        jobs[job_id]["status"] = "CANCELLED"
        jobs[job_id]["speed"] = "0 MB/s"
        title = jobs[job_id].get("title", job_id)
        print(f"[Scraper] User cancelled job: {title} (ID: {job_id})")
        return jsonify({"status": "cancelled", "job_id": job_id}), 200

    return jsonify({"error": "Job not found"}), 404


@app.route("/api/downloads/<job_id>", methods=["DELETE", "POST", "OPTIONS"])
@app.route("/api/downloads/<job_id>/delete", methods=["POST", "DELETE", "OPTIONS"])
def delete_job(job_id):
    if request.method == "OPTIONS":
        return "", 200

    with queue_lock:
        for item in list(download_queue):
            if item.get("job_id") == job_id:
                download_queue.remove(item)
        active_jobs.discard(job_id)
        update_queued_job_positions()
        process_next_in_queue()

    # Cancel if active
    event = job_cancel_events.get(job_id)
    if event:
        event.set()

    driver = job_drivers.get(job_id)
    if driver:
        try:
            driver.quit()
        except Exception:
            pass

    job_cancel_events.pop(job_id, None)
    job_drivers.pop(job_id, None)

    if job_id in jobs:
        title = jobs[job_id].get("title", job_id)
        del jobs[job_id]
        print(f"[Scraper] Removed job from history: {title} (ID: {job_id})")
        return jsonify({"status": "deleted", "job_id": job_id}), 200

    return jsonify({"error": "Job not found"}), 404


@app.route("/api/downloads/settings", methods=["GET", "POST", "OPTIONS"])
def download_settings():
    global MAX_CONCURRENT_DOWNLOADS
    if request.method == "OPTIONS":
        return "", 200

    if request.method == "POST":
        data = request.json or {}
        new_max = data.get("max_concurrent")
        if new_max is not None:
            try:
                MAX_CONCURRENT_DOWNLOADS = max(1, min(int(new_max), 5))
                print(f"[Queue] Concurrency limit updated to: {MAX_CONCURRENT_DOWNLOADS}")
                with queue_lock:
                    process_next_in_queue()
            except (ValueError, TypeError):
                pass

    with queue_lock:
        return jsonify({
            "max_concurrent": MAX_CONCURRENT_DOWNLOADS,
            "active_count": len(active_jobs),
            "queued_count": len(download_queue),
        }), 200


@app.route("/api/downloads/clear-completed", methods=["POST", "DELETE", "OPTIONS"])
def clear_completed_downloads():
    if request.method == "OPTIONS":
        return "", 200

    cleared = []
    for jid, job in list(jobs.items()):
        if job.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
            cleared.append(jid)
            del jobs[jid]

    print(f"[Scraper] Cleared {len(cleared)} finished jobs from history.")
    return jsonify({"cleared": cleared, "count": len(cleared)}), 200



@app.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify(list(log_buffer))


@app.route("/plugins/<path:filename>", methods=["GET"])
def serve_plugins(filename):
    """Serve Jellyfin plugin repository manifest and packages."""
    plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
    if not os.path.exists(os.path.join(plugins_dir, filename)):
        # Fallback to ../jellyfin-plugin-autofix
        fallback_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "jellyfin-plugin-autofix"))
        if os.path.exists(os.path.join(fallback_dir, filename)):
            return send_from_directory(fallback_dir, filename)
    return send_from_directory(plugins_dir, filename)


def auto_clean_existing_libraries():
    time.sleep(3)
    print("[Cleaner] Running automatic dot-to-space check on media libraries...")
    for path in [HOLLYWOOD_DIR, BOLLYWOOD_DIR]:
        if os.path.exists(path):
            try:
                rename_clean_dots.rename_media_in_dir(path)
            except Exception as e:
                print(f"[Cleaner] Error scanning {path}: {e}")
    print("[Cleaner] Media libraries check complete.")

threading.Thread(target=auto_clean_existing_libraries, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
