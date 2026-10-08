from flask import Flask, request, jsonify
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
        if clean:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_buffer.append(f"[{timestamp}] {clean}")

    def flush(self):
        self.original_stdout.flush()

sys.stdout = LogInterceptor(sys.stdout)

SEERR_API_KEY = "MTc5MTAzMzU5ODIwM2ZkZDA3YmM5LTQ2OTctNDYyMy1iZGZmLTgyZGE5NzhiOWE2MA=="
SEERR_API_URL = os.environ.get("SEERR_API_URL", "http://seerr:5055/api/v1")
INDIAN_LANGUAGES = {"hi", "ta", "te", "ml", "kn", "pa", "bn", "mr", "gu", "ur"}

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
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


job_cancel_events = {}
job_drivers = {}


def run_scraper_job(job_id, movie_title, tmdb_id, poster_path, preferred_quality="1080p", is_indian=None, download_folder=None):
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
        )

    except (KeyboardInterrupt, Exception) as e:
        if cancel_event.is_set():
            print(f"[Scraper] Job {job_id} was successfully cancelled.")
            if job_id in jobs:
                jobs[job_id]["status"] = "CANCELLED"
                jobs[job_id]["speed"] = "0 MB/s"
        else:
            print(f"Scraper error: {e}")
            if job_id in jobs:
                jobs[job_id]["status"] = "FAILED"
                jobs[job_id]["error"] = str(e)
    finally:
        driver = job_drivers.pop(job_id, None)
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        job_cancel_events.pop(job_id, None)


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    media = data.get("media")

    if not media:
        return jsonify({"status": "ignored"}), 200

    movie_title = data.get("subject", "Unknown Movie")
    tmdb_id = media.get("tmdbId") or "unknown"
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
        "status": "SEARCHING",
        "progress": 0,
        "speed": "0 MB/s",
        "source": site_source,
        "destination": dest_folder,
        "startedAt": "Just now",
    }

    thread = threading.Thread(
        target=run_scraper_job,
        args=(job_id, movie_title, tmdb_id, poster_path, preferred_quality, is_indian, dest_folder),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "status": "received",
        "job_id": job_id,
        "quality": preferred_quality,
        "source": site_source,
        "destination": dest_folder
    }), 200


@app.route("/api/downloads", methods=["GET"])
def get_downloads():
    return jsonify(list(jobs.values()))


@app.route("/api/downloads/<job_id>/cancel", methods=["POST", "OPTIONS"])
def cancel_job(job_id):
    if request.method == "OPTIONS":
        return "", 200

    if job_id in jobs:
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


@app.route("/api/downloads/<job_id>", methods=["DELETE", "OPTIONS"])
def delete_job(job_id):
    if request.method == "OPTIONS":
        return "", 200

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


@app.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify(list(log_buffer))


@app.route("/", methods=["GET"])
def home():
    return "Webhook server is running!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
