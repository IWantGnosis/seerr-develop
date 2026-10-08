from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import os
import re
import time
import tempfile
import shutil
import urllib.request
from urllib.parse import urlparse, parse_qs


def get_download_folder():
    folder = os.environ.get("DOWNLOAD_FOLDER")
    if not folder:
        # Default to standard Downloads directory on Windows or Linux
        folder = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(folder, exist_ok=True)
    return folder


DOWNLOAD_FOLDER = get_download_folder()


def create_driver(headless=False, download_folder=None):
    """
    Creates a stealth Chrome/Brave WebDriver instance.
    Cross-platform compatible with Windows and Linux.
    Defaults to headless=False so the browser UI is visible.
    Can be overridden via SCRAPER_HEADLESS environment variable (1/true).
    """
    env_headless = os.environ.get("SCRAPER_HEADLESS", "").lower()
    if env_headless in ("1", "true", "yes"):
        headless = True
    elif env_headless in ("0", "false", "no"):
        headless = False

    options = webdriver.ChromeOptions()

    # 1. Headless & display configuration
    if headless:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-maximized")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--remote-debugging-pipe")
    options.add_argument("--disable-features=OptimizationHints,Translate,MediaRouter")
    options.add_argument("--log-level=3")

    # Isolated unique profile for Docker sessions (prevents DevToolsActivePort & SingletonLock collisions)
    profile_dir = tempfile.mkdtemp(prefix="chrome_ud_")
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--disk-cache-dir={profile_dir}/cache")

    # 2. Stealth & Anti-bot evasion
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    # Realistic desktop User-Agent
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
    options.add_argument(f"user-agent={user_agent}")

    target_dir = download_folder or DOWNLOAD_FOLDER
    os.makedirs(target_dir, exist_ok=True)

    # Download preferences
    prefs = {
        "download.default_directory": target_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    options.add_experimental_option("prefs", prefs)

    # Load uBlock Origin extension if available (eliminates ads and click blockers)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ublock_candidates = [
        os.path.join(script_dir, "..", "extension", "uBlock.crx"),
        os.path.join(script_dir, "extension", "uBlock.crx"),
        r"C:\Users\naksh\Downloads\torrent-notify\extension\uBlock.crx",
    ]
    for ext_path in ublock_candidates:
        if os.path.exists(ext_path):
            try:
                options.add_extension(ext_path)
                print(f"[Scraper] Loaded adblocker extension: {ext_path}")
                break
            except Exception:
                pass

    # Cross-platform browser detection: Brave, Chrome, or Chromium (Linux / Docker)
    brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    if os.path.exists(brave_path):
        options.binary_location = brave_path
    elif os.environ.get("CHROME_BIN"):
        options.binary_location = os.environ.get("CHROME_BIN")
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"
    elif os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/google-chrome"):
        options.binary_location = "/usr/bin/google-chrome"

    # ChromeDriver path detection (Linux / Docker)
    driver_path = os.environ.get("CHROMEDRIVER_PATH")
    if not driver_path:
        for candidate in ["/usr/bin/chromedriver", "/usr/lib/chromium-browser/chromedriver"]:
            if os.path.exists(candidate):
                driver_path = candidate
                break

    service = Service(executable_path=driver_path, log_output=os.devnull) if driver_path else Service(log_output=os.devnull)
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"[Driver] Pipe mode launch exception: {e}. Retrying with remote port mode...")
        time.sleep(1)
        # Fallback without --remote-debugging-pipe
        options.arguments = [a for a in options.arguments if a != "--remote-debugging-pipe"]
        options.add_argument("--remote-debugging-port=0")
        driver = webdriver.Chrome(service=service, options=options)

    driver._profile_dir = profile_dir

    # 3. Stealth JavaScript overrides
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """
    })

    # 4. Inject MoviesMod Auto-Downloader & Bypasser (Predator engine with 10x Timer Hook)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            (function() {
                // --- 1. Fast Timer Hook (10x Speedup on all countdown timers) ---
                const TIMER_SPEED = 0.1;
                function scaleDelay(delay) {
                    const d = Number(delay);
                    if (!Number.isFinite(d) || d <= 0) return delay;
                    return Math.max(1, Math.round(d * TIMER_SPEED));
                }
                const rawSetTimeout = window.setTimeout;
                const rawSetInterval = window.setInterval;
                window.setTimeout = function (callback, delay, ...args) {
                    return rawSetTimeout.call(this, callback, scaleDelay(delay), ...args);
                };
                window.setInterval = function (callback, delay, ...args) {
                    return rawSetInterval.call(this, callback, scaleDelay(delay), ...args);
                };

                // --- 2. Automated Gateway Bypasser ---
                function runWorkflow() {
                    const host = window.location.hostname || '';

                    // A. modpro.blog / leechpro.blog: auto-follow sid link (same tab)
                    if (host.includes('modpro.blog') || host.includes('leechpro.blog')) {
                        const sidLink = document.querySelector("a[href*='sid=']:not(.alert a)") || document.querySelector("a[href*='sid=']");
                        if (sidLink && !sidLink.dataset.labFollowed) {
                            sidLink.dataset.labFollowed = 'true';
                            sidLink.removeAttribute('target');
                            const href = sidLink.href || sidLink.getAttribute('href');
                            if (href && !href.startsWith('javascript:')) {
                                window.location.replace(href);
                                return;
                            }
                        }
                    }

                    // B. unblockedgames.world workflow
                    if (host.includes('unblockedgames')) {
                        // 1. Submit landing form
                        const landing = document.querySelector('form#landing');
                        if (landing && !landing.dataset.labSubmitted) {
                            landing.dataset.labSubmitted = 'true';
                            landing.submit();
                            return;
                        }
                        // 2. Click verify2 or verify button
                        const verify2 = document.querySelector('#verify_button2');
                        if (verify2 && !verify2.dataset.labClicked) {
                            verify2.dataset.labClicked = 'true';
                            verify2.click();
                        }
                        const verify = document.querySelector('#verify_button');
                        if (verify && !verify.dataset.labClicked) {
                            verify.dataset.labClicked = 'true';
                            verify.click();
                        }
                        // 3. Download link #two_steps_btn
                        const twoSteps = document.querySelector('#two_steps_btn');
                        if (twoSteps) {
                            twoSteps.removeAttribute('target');
                            const href = twoSteps.href || twoSteps.getAttribute('href');
                            if (href && href !== '' && !href.startsWith('javascript:') && href !== '#' && !href.endsWith('#')) {
                                twoSteps.click();
                            }
                        }
                    }

                    // C. thenaukriadda.in workflow
                    if (host.includes('thenaukriadda')) {
                        // 1. Submit initial form
                        const lpLand = document.querySelector('form#landing, form#lp-land') || 
                                       document.querySelector("input[name='_wp_http'], input[name='_lp_http']")?.closest('form');
                        if (lpLand && !lpLand.dataset.labSubmitted) {
                            lpLand.dataset.labSubmitted = 'true';
                            lpLand.submit();
                            return;
                        }
                        // 2. Generate button
                        const genBtn = document.querySelector('#lp-btn-generate');
                        if (genBtn && !genBtn.dataset.labClicked) {
                            genBtn.dataset.labClicked = 'true';
                            genBtn.click();
                        }
                        // 3. Continue button
                        const contBtn = document.querySelector('#lp-btn-continue') || document.querySelector('button.lp-btn:not(#lp-btn-generate)');
                        if (contBtn && !contBtn.dataset.labClicked) {
                            contBtn.dataset.labClicked = 'true';
                            contBtn.click();
                        }
                        // 4. Download button
                        const goBtn = document.querySelector('#lp-btn-go') || document.querySelector("a[href*='driveseed'], a[href*='video-seed']");
                        if (goBtn) {
                            goBtn.removeAttribute('target');
                            const href = goBtn.href || goBtn.getAttribute('href');
                            if (href && !href.startsWith('javascript:') && href !== '#') {
                                goBtn.click();
                            }
                        }
                    }

                    // D. DriveSeed / DriveLeech: auto-click video-gen / workerseed
                    if (host.includes('driveseed') || host.includes('driveleech')) {
                        if (window.location.pathname.startsWith('/file/')) {
                            const dlLink = document.querySelector("a[href*='video-gen']") || 
                                           document.querySelector("a[href*='workerseed']") ||
                                           document.querySelector("a[href*='zfile']") ||
                                           document.querySelector(".btn-danger");
                            if (dlLink && !dlLink.dataset.labClicked) {
                                dlLink.dataset.labClicked = 'true';
                                dlLink.removeAttribute('target');
                                dlLink.click();
                            }
                        }
                    }

                    // E. video-seed.dev / workerseed.dev / video-gen.xyz: auto-click final download button
                    if (host.includes('video-seed') || host.includes('workerseed') || host.includes('video-gen')) {
                        const finalBtn = document.querySelector('#ins, #download, a.btn-danger, button.btn-danger, a.btn');
                        if (finalBtn && !finalBtn.dataset.labClicked) {
                            finalBtn.dataset.labClicked = 'true';
                            finalBtn.removeAttribute('target');
                            finalBtn.click();
                        }
                    }
                }

                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', runWorkflow);
                } else {
                    runWorkflow();
                }
                window.addEventListener('load', runWorkflow);
                setInterval(runWorkflow, 300);
            })();
        """
    })

    # 5. Enable file downloads via Chrome DevTools Protocol
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": DOWNLOAD_FOLDER
    })

    # 6. Block ad networks and safeframe iframes
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setBlockedURLs", {
            "urls": [
                "*googlesyndication.com*",
                "*safeframe.googlesyndication.com*",
                "*doubleclick.net*",
                "*googleads.g.doubleclick.net*",
                "*adservice.google.*",
                "*adnxs.com*",
                "*popads.net*",
                "*propellerads.com*",
            ]
        })
    except Exception:
        pass

    # Ensure headless Chromium permits automatic file downloads into target_dir
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": target_dir
        })
    except Exception:
        pass
    try:
        driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": target_dir
        })
    except Exception:
        pass

    return driver


def safe_click(driver, element):
    """
    Safely clicks an element using JavaScript after removing any overlays,
    scrolling it into view, and ensuring ad iframes can't intercept the click.
    """
    try:
        # 1. Clean up floating ad iframes and sticky overlays
        driver.execute_script("""
            document.querySelectorAll('iframe, div[id*="google_ads"], ins.adsbygoogle, div[class*="overlay"]').forEach(el => {
                if (!el.querySelector('button') && !el.querySelector('a')) {
                    el.remove();
                }
            });
        """)
        # 2. Scroll into center view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
        time.sleep(0.3)
        # 3. Trigger JS click (never intercepted by WebDriver)
        driver.execute_script("arguments[0].click();", element)
    except Exception:
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].form ? arguments[0].form.submit() : arguments[0].click();", element)










def clean_filename_dots(name):
    """
    Replaces all dots in the filename base with spaces (preserving file extension).
    Example: 'Minions.and.Monsters.2026.mkv' -> 'Minions and Monsters 2026.mkv'
    """
    base, ext = os.path.splitext(name)
    cleaned_base = base.replace('.', ' ')
    cleaned_base = re.sub(r'\s+', ' ', cleaned_base).strip()
    return f"{cleaned_base}{ext}"


def download_stream_direct(url, target_folder, default_name, total_size=None, progress_callback=None, cancel_event=None, cookies_str=None, bar_width=30):
    """
    Downloads direct video link using Python streaming chunks.
    Bypasses headless Chrome download restrictions, reports live progress,
    and supports instant user cancellation.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://video-seed.dev/",
    }
    if cookies_str:
        headers["Cookie"] = cookies_str

    clean_url = url.split("#")[0].strip()
    print(f"[Downloader] Opening direct download stream...")
    req = urllib.request.Request(clean_url, headers=headers)

    with urllib.request.urlopen(req, timeout=30) as resp:
        content_disp = resp.headers.get("Content-Disposition", "")
        ext = ".mkv"
        raw_fn = None
        if "filename=" in content_disp:
            m = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disp)
            if m:
                raw_fn = m.group(1).strip()
                _, e = os.path.splitext(raw_fn)
                if e.lower() in [".mkv", ".mp4", ".avi"]:
                    ext = e.lower()

        if default_name:
            safe_name = re.sub(r'[\\/*?:"<>|]', "", default_name).strip()
            if not safe_name.lower().endswith(('.mkv', '.mp4', '.avi')):
                safe_name += ext
            filename = safe_name
        elif raw_fn:
            filename = raw_fn
        else:
            filename = f"movie{ext}"

        # Replace dots with spaces in the movie filename (except the extension)
        filename = clean_filename_dots(filename)

        if not total_size:
            length = resp.headers.get("Content-Length")
            if length:
                total_size = int(length)

        final_path = os.path.join(target_folder, filename)
        part_path = final_path + ".crdownload"
        print(f"[Downloader] Destination file: {final_path}")
        if total_size:
            print(f"[Downloader] File size: {total_size / (1024 * 1024):.1f} MB")

        downloaded_bytes = 0
        start_time = time.time()
        last_print_time = start_time
        last_print_bytes = 0

        try:
            with open(part_path, "wb") as f:
                while True:
                    if cancel_event and cancel_event.is_set():
                        print("\n[Downloader] Download cancelled by user.")
                        f.close()
                        try:
                            os.remove(part_path)
                        except Exception:
                            pass
                        raise KeyboardInterrupt("Download cancelled by user")

                    chunk = resp.read(1024 * 512)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded_bytes += len(chunk)

                    now = time.time()
                    if now - last_print_time >= 0.5:
                        elapsed = now - last_print_time
                        speed = (downloaded_bytes - last_print_bytes) / elapsed if elapsed > 0 else 0
                        speed_mb = speed / (1024 * 1024)
                        current_mb = downloaded_bytes / (1024 * 1024)

                        if total_size and total_size > 0:
                            total_mb = total_size / (1024 * 1024)
                            percent = min((downloaded_bytes / total_size) * 100, 100)
                            remaining = max(total_size - downloaded_bytes, 0)
                            eta_sec = remaining / speed if speed > 0 else None
                            eta_str = format_eta(eta_sec)
                            filled = int(bar_width * percent / 100)
                            bar = "#" * filled + "-" * (bar_width - filled)
                            print(
                                f"\r[{bar}] {percent:5.1f}% | {current_mb:.1f}/{total_mb:.1f} MB | {speed_mb:.2f} MB/s | ETA {eta_str}",
                                end="",
                                flush=True
                            )
                            if progress_callback:
                                progress_callback(percent, f"{speed_mb:.2f} MB/s", "DOWNLOADING")
                        else:
                            filled = int(time.time() * 4) % bar_width
                            bar = "".join("#" if i == filled else "-" for i in range(bar_width))
                            print(
                                f"\r[{bar}] {current_mb:.2f} MB | {speed_mb:.2f} MB/s | downloading",
                                end="",
                                flush=True
                            )
                            if progress_callback:
                                progress_callback(50.0, f"{speed_mb:.2f} MB/s", "DOWNLOADING")

                        last_print_time = now
                        last_print_bytes = downloaded_bytes
        except Exception:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except Exception:
                    pass
            raise

        if os.path.exists(final_path):
            try:
                os.remove(final_path)
            except Exception:
                pass
        os.rename(part_path, final_path)
        print(f"\n[Downloader] Download complete: {filename}")
        if progress_callback:
            progress_callback(100.0, "0 MB/s", "COMPLETED")
        return final_path


def get_remote_file_size(url, timeout=8):
    """
    HEAD request to read Content-Length before the download starts.
    Just reads a header - does not fetch the file itself.
    Returns None if the server doesn't provide it (some hosts omit it).
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            length = resp.headers.get("Content-Length")
            return int(length) if length else None
    except Exception:
        return None


def format_eta(seconds):
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "--:--"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def wait_for_download(download_folder, before_files, total_size=None,
                       poll_interval=0.3, stable_checks=3, bar_width=30,
                       progress_callback=None, cancel_event=None,
                       download_start_timeout=120):
    """
    Watches for a NEW file (not present in `before_files`) to appear in
    download_folder, tracks it through the .crdownload -> final rename,
    and prints a live progress bar + speed + ETA until the size is stable.
    If `total_size` (bytes) is known, the bar shows a real percentage and
    a real ETA; otherwise it falls back to a size/speed-only display.
    """
    target_path = None
    is_crdownload = False
    previous_size = -1
    previous_time = time.time()
    stable_count = 0
    wait_start = time.time()
    diagnostics_printed = False

    print("Waiting for download to start...")

    while True:
        if cancel_event and cancel_event.is_set():
            if target_path and is_crdownload and os.path.exists(target_path):
                try:
                    os.remove(target_path)
                    print(f"\n[Scraper] Removed incomplete download: {target_path}")
                except Exception:
                    pass
            raise KeyboardInterrupt("Download cancelled by user")

        current_files = set(os.listdir(download_folder))
        new_files = current_files - before_files

        # Step 1: find our file (not yet identified)
        if target_path is None:
            waited = time.time() - wait_start
            if waited > download_start_timeout:
                print(f"\n[Scraper] Download did not start within {download_start_timeout}s timeout. Aborting.")
                raise TimeoutError("Download failed to initiate within timeout")

            # Heartbeat + diagnostics: if nothing new shows up within 8s,
            # print exactly what's in the folder so this never hangs silently.
            if waited > 8 and not diagnostics_printed:
                print(f"\nStill nothing new after {waited:.1f}s.")
                print(f"  Watching folder: {download_folder}")
                print(f"  Files present before download: {sorted(before_files)}")
                print(f"  Files present now:              {sorted(current_files)}")
                print("  (If the file you expect is already in the 'before' list, "
                      "the download started earlier than expected - the snapshot "
                      "needs to move even earlier in the click sequence.)")
                diagnostics_printed = True

            new_crdownloads = [f for f in new_files if f.endswith(".crdownload")]
            if new_crdownloads:
                target_path = os.path.join(download_folder, new_crdownloads[0])
                is_crdownload = True
            else:
                new_finals = [f for f in new_files if not f.endswith(".crdownload")]
                if new_finals:
                    target_path = os.path.join(download_folder, new_finals[0])
                    is_crdownload = False
            time.sleep(poll_interval)
            continue

        # Step 2: handle the crdownload -> final rename
        if is_crdownload:
            final_name = os.path.basename(target_path)
            if final_name.endswith(".crdownload"):
                final_name = final_name[: -len(".crdownload")]
            final_path = os.path.join(download_folder, final_name)

            # If the final file already exists on disk and is populated (> 10MB)
            if os.path.exists(final_path) and os.path.getsize(final_path) > 10 * 1024 * 1024:
                target_path = final_path
                is_crdownload = False
                previous_size = -1
                stable_count = 0
            elif not os.path.exists(target_path):
                if os.path.exists(final_path):
                    target_path = final_path
                    is_crdownload = False
                    previous_size = -1
                    stable_count = 0
                else:
                    time.sleep(poll_interval)
                    continue

        if not os.path.exists(target_path):
            time.sleep(poll_interval)
            continue

        current_size = os.path.getsize(target_path)
        current_time = time.time()

        if previous_size == -1:
            previous_size = current_size
            previous_time = current_time
            time.sleep(poll_interval)
            continue

        bytes_downloaded = current_size - previous_size
        time_elapsed = current_time - previous_time
        speed = bytes_downloaded / time_elapsed if time_elapsed > 0 else 0
        speed_mb = speed / (1024 * 1024)
        current_mb = current_size / (1024 * 1024)

        if total_size:
            total_mb = total_size / (1024 * 1024)
            percent = min(current_size / total_size * 100, 100)
            
            filled_len = int(bar_width * percent / 100)
            bar = "#" * filled_len + "-" * (bar_width - filled_len)
            remaining_bytes = max(total_size - current_size, 0)
            eta_seconds = (remaining_bytes / speed) if speed > 0 else None
            eta_str = format_eta(eta_seconds)
            status = "downloading" if is_crdownload else "finalizing"
            print(
                f"\r[{bar}] {percent:5.1f}% | {current_mb:.1f}/{total_mb:.1f} MB "
                f"| {speed_mb:.2f} MB/s | ETA {eta_str} | {status}",
                end="",
                flush=True
            )
            if progress_callback:
                progress_callback(percent, f"{speed_mb:.2f} MB/s", "DOWNLOADING")
        else:
            # Total size unknown (server didn't send Content-Length) -
            # fall back to an animated bar with size/speed only.
            filled = int(time.time() * 4) % bar_width
            bar = "".join("#" if i == filled else "-" for i in range(bar_width))
            status = "downloading" if is_crdownload else "finalizing"
            print(
                f"\r[{bar}] {current_mb:.2f} MB | {speed_mb:.2f} MB/s | {status}",
                end="",
                flush=True
            )
            if progress_callback:
                progress_callback(50.0, f"{speed_mb:.2f} MB/s", "DOWNLOADING")

        # Track stability
        if current_size == previous_size:
            stable_count += 1
        else:
            stable_count = 0

        # Complete if size is stable and:
        # 1. Not a crdownload, OR
        # 2. total_size is reached (>= 99.5%), OR
        # 3. size has been unchanged for at least 8 checks
        has_finished_bytes = bool(total_size and current_size >= total_size * 0.995)
        if (not is_crdownload or has_finished_bytes or stable_count >= 8) and stable_count >= stable_checks:
            final_name = os.path.basename(target_path)
            if final_name.endswith(".crdownload"):
                final_name = final_name[: -len(".crdownload")]
            final_path = os.path.join(download_folder, final_name)

            if is_crdownload and os.path.exists(target_path):
                try:
                    if os.path.exists(final_path) and os.path.getsize(final_path) > 10 * 1024 * 1024:
                        os.remove(target_path)
                    else:
                        os.rename(target_path, final_path)
                    target_path = final_path
                except Exception:
                    pass

            cleaned_final = clean_filename_dots(os.path.basename(target_path))
            if cleaned_final != os.path.basename(target_path):
                new_final_path = os.path.join(download_folder, cleaned_final)
                try:
                    os.rename(target_path, new_final_path)
                    target_path = new_final_path
                except Exception:
                    pass

            # Clean any leftover orphan .crdownload files for this movie
            try:
                base_stem = os.path.splitext(os.path.basename(target_path))[0]
                for f in os.listdir(download_folder):
                    if f.endswith(".crdownload") and (base_stem[:15].lower() in f.lower()):
                        try:
                            os.remove(os.path.join(download_folder, f))
                        except Exception:
                            pass
            except Exception:
                pass

            print(f"\n[Downloader] Download complete: {os.path.basename(target_path)}")
            if progress_callback:
                progress_callback(100.0, "0 MB/s", "COMPLETED")
            break

        previous_size = current_size
        previous_time = current_time
        time.sleep(poll_interval)

    return target_path












#This is my Code i written with the help of chatgpt to learns some stuff but it was helpfull


from difflib import SequenceMatcher

def clean_movie_title(text):
    """Extracts just the core movie title, stripping leading 'Download' and trailing metadata."""
    t = re.sub(r'(?i)^download\s+', '', text.strip())
    # Take part before (year) or [quality] or {audio}
    t = re.split(r'[\(\[\{]', t)[0].strip()
    # Remove trailing colons, dashes or whitespace
    t = re.sub(r'[:\-\s]+$', '', t).strip()
    return t


def find_best_movie_match(results, target_title):
    """
    Finds the index of the movie result that best matches target_title (e.g. 'Dune (2021)').
    Compares:
      1. Clean Movie Title: exact match receives +300 points.
      2. String similarity & word overlap.
      3. Extra word penalty (prevents 'Devil in Dune' or 'Planet Dune' matching 'Dune').
      4. TV Show / Season penalty if searching for a movie.
      5. Release Year matching (+200 exact, -200 mismatch).
    """
    if not results:
        return 0, 0

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", target_title)
    target_year = year_match.group(1) if year_match else None

    target_clean = clean_movie_title(target_title)
    target_norm = re.sub(r"[^\w\s]", "", target_clean).lower().strip()
    target_words = set(target_norm.split())

    best_idx = 0
    best_score = -999999

    for idx, item in enumerate(results):
        card_raw = item.get("title", "")
        card_clean = clean_movie_title(card_raw)
        card_norm = re.sub(r"[^\w\s]", "", card_clean).lower().strip()
        card_words = set(card_norm.split())

        card_year_match = re.search(r"\b(19\d{2}|20\d{2})\b", card_raw)
        card_year = card_year_match.group(1) if card_year_match else None

        score = 0

        # 1. Exact clean title match
        if target_norm == card_norm:
            score += 300
        else:
            # Similarity ratio (0.0 to 1.0)
            sim = SequenceMatcher(None, target_norm, card_norm).ratio()
            score += int(sim * 100)
            # Penalty for each extra word in card title not in target
            extra_words = card_words - target_words
            score -= len(extra_words) * 60

        # 2. Penalty if this is a TV Show (Season/Series)
        if re.search(r"(?i)\b(season\s*\d+|s\d+|series|episodes?)\b", card_raw):
            score -= 200

        # 3. Year matching
        if target_year and card_year:
            if target_year == card_year:
                score += 200
            else:
                score -= 200
        elif target_year and not card_year:
            score -= 50

        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx, best_score


def find_best_quality_link(links, preferred_quality="1080p"):
    """
    Selects the optimal download link with target file size in the 5 GB - 10 GB sweet spot:
    - Strictly avoids low-resolution options: 480p and 720p receive heavy penalties.
    - Favors 1080p and 2160p (4K).
    - Prevents giant bloated files (>12 GB, e.g. 19 GB files are heavily penalized).
    - Rewards 10-bit color formats.
    - Favors standard, normal compatible video encodings (AVC/x264/standard WEB-DL/BluRay) over HEVC-only.
    """
    if not links:
        return 0, 0

    pref = preferred_quality.lower()
    is_4k_pref = "4k" in pref or "2160" in pref

    best_idx = 0
    best_score = -999999

    for idx, item in enumerate(links):
        title = item.get("link_title", "").lower()
        score = 0

        # 1. Parse File Size from title (e.g. "[6.5GB]", "[19.2GB]", "[950MB]")
        size_gb = None
        size_match = re.search(r"\[([\d.]+)\s*(gb|mb)\]", title)
        if size_match:
            val = float(size_match.group(1))
            unit = size_match.group(2).lower()
            size_gb = val if unit == "gb" else val / 1024

        # 2. Resolution Matching & Strict Penalties
        # Strictly reject or heavily penalize 480p and 720p
        if "480p" in title:
            score -= 600
        elif "720p" in title:
            score -= 500

        # Preferred Resolutions: 1080p and 2160p (4K)
        has_4k = any(k in title for k in ["2160p", "4k", "uhd"])
        has_1080p = "1080p" in title

        if is_4k_pref:
            if has_4k:
                score += 300
            elif has_1080p:
                score += 150
        else:
            if has_1080p:
                score += 300
            elif has_4k:
                score += 200

        # 3. File Size Scoring (Target: ~5 GB to 10 GB)
        if size_gb is not None:
            if 5.0 <= size_gb <= 10.5:
                # Sweet spot requested: approx 5 to 10 GB
                score += 250
            elif 3.5 <= size_gb < 5.0:
                # Acceptable high-quality 1080p
                score += 100
            elif 10.5 < size_gb <= 12.5:
                # Slightly above 10GB but reasonable for 4K
                score += 40
            elif size_gb > 14.0:
                # Massive bloated files (like 19 GB) get heavily penalized
                score -= 400
            elif size_gb < 2.5:
                # Too small / low bitrate
                score -= 150
        else:
            # If size is not specified in title, slightly prefer 1080p
            if has_1080p:
                score += 50

        # 4. Color Depth: 10-bit bonus
        if "10bit" in title or "10-bit" in title:
            score += 40

        # 5. Encoding & Source Preferences
        # Prefer normal, highly-compatible releases (BluRay, WEB-DL)
        if "bluray" in title or "web-dl" in title or "org" in title:
            score += 20
        elif "webrip" in title:
            score += 10

        # HEVC / x265: avoid giving it unfair advantage over standard normal formats
        if "hevc" in title or "x265" in title:
            score -= 10

        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx, best_score


def bypass_verification_gateways(driver, max_wait=45):
    """
    Swiftly bypasses MoviesMod link verification gateways:
    - thenaukriadda.in / en.thenaukriadda.in
    - unblockedgames.world / cloud.unblockedgames.world / tech.unblockedgames.world
    - techmny.com / en.techmny.com
    - examdegree.site / tech.examdegree.site
    - sharpcornerr.in / tech.sharpcornerr.in
    - oddfirm.com
    - links.modpro.blog / episodes.modpro.blog

    Handles #landing forms, #verify_button (skipping timers), #two_steps_btn tab opening,
    and extracts destination DriveSeed/VideoSeed links.
    """
    start_time = time.time()
    print(f"[Bypass] Initiating gateway bypass on: {driver.current_url}")

    while time.time() - start_time < max_wait:
        # Check all open tabs to see if destination is already reached
        if len(driver.window_handles) > 1:
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                cur = driver.current_url
                if any(h in cur for h in ["driveseed", "video-seed", "drivedownload", "video-downloads"]):
                    print(f"[Bypass] Reached destination in tab: {cur}")
                    return cur
            driver.switch_to.window(driver.window_handles[-1])

        cur_url = driver.current_url

        # 1. Have we already reached DriveSeed or VideoSeed?
        if any(h in cur_url for h in ["driveseed", "video-seed", "drivedownload", "video-downloads"]):
            print(f"[Bypass] Reached destination URL: {cur_url}")
            return cur_url

        # 2. Check if a direct destination link is visible in the DOM
        try:
            drive_elements = driver.find_elements(
                By.XPATH,
                "//a[contains(@href, 'driveseed') or contains(@href, 'video-seed') or contains(@href, 'drivedownload')]"
            )
            for el in drive_elements:
                href = el.get_attribute("href")
                if href and any(h in href for h in ["driveseed", "video-seed", "drivedownload"]):
                    print(f"[Bypass] Found direct destination link in DOM: {href}")
                    return href
        except Exception:
            pass

        # 3. Handle modpro.blog: click fast server / sid link
        if any(h in cur_url for h in ["modpro.blog", "mflixblog"]):
            try:
                sid_el = driver.find_element(
                    By.XPATH,
                    "//a[contains(@class, 'maxbutton-1')] | //a[contains(@class, 'maxbutton')] | //a[contains(@href, 'sid=')]"
                )
                href = sid_el.get_attribute("href")
                if href and href != cur_url and not href.endswith("#"):
                    print(f"[Bypass] Following modpro button: {href}")
                    driver.get(href)
                    time.sleep(1.5)
                    continue
            except Exception:
                pass

        # 4. Handle Step 1: Submit #landing or .lp-form immediately
        try:
            landing = driver.find_elements(By.ID, "landing")
            if landing:
                print("[Bypass] Submitting landing form...")
                driver.execute_script("document.querySelector('#landing').submit();")
                time.sleep(2)
                continue
            
            lp_form = driver.find_elements(By.CSS_SELECTOR, "form[action*='lp'], form.lp-form")
            if lp_form:
                print("[Bypass] Submitting LP form...")
                driver.execute_script("document.querySelector('form[action*=\"lp\"], form.lp-form').submit();")
                time.sleep(2)
                continue
        except Exception:
            pass

        # 5. Handle Step 2: Click #verify_button directly (skipping countdowns)
        try:
            verify_buttons = driver.find_elements(
                By.XPATH,
                "//button[@id='verify_button'] | //button[contains(@class, 'lp-btn')] | //button[normalize-space(.)='Click here to continue'] | //button[@id='btn6']"
            )
            for vb in verify_buttons:
                if vb.is_displayed() or not vb.get_attribute("data-clicked"):
                    print("[Bypass] Clicking verify button...")
                    driver.execute_script("arguments[0].setAttribute('data-clicked', 'true'); arguments[0].click();", vb)
                    time.sleep(1.5)
                    break
        except Exception:
            pass

        # 6. Handle Step 3: Check #two_steps_btn
        try:
            two_steps = driver.find_elements(By.ID, "two_steps_btn")
            if two_steps:
                ts_el = two_steps[0]
                href = ts_el.get_attribute("href")
                if href and href != "" and not href.startswith("javascript") and href != "#":
                    print(f"[Bypass] Clicking two_steps_btn with link: {href}")
                    driver.execute_script("arguments[0].click();", ts_el)
                    time.sleep(2)
                    if len(driver.window_handles) > 1:
                        driver.switch_to.window(driver.window_handles[-1])
                    if any(h in driver.current_url for h in ["driveseed", "video-seed", "drivedownload"]):
                        return driver.current_url
        except Exception:
            pass

        # 7. Check for script-embedded URLs (unblockedgames / thenaukriadda pattern)
        try:
            page_source = driver.page_source
            match_script = re.search(r'c\.setAttribute\("href",\s*"(https?://[^"]+)"\)', page_source)
            if match_script:
                script_link = match_script.group(1)
                if any(h in script_link for h in ["driveseed", "video-seed", "drivedownload"]):
                    print(f"[Bypass] Extracted destination from script: {script_link}")
                    return script_link
                elif "?go=" in script_link and script_link != cur_url:
                    print(f"[Bypass] Navigating to script go_url: {script_link}")
                    driver.get(script_link)
                    time.sleep(2)
                    continue

            match_loc = re.search(r'(?:window\.location(?:\.href)?|location\.assign)\s*=\s*["\'](https?://[^"\']*(?:driveseed|video-seed|drivedownload)[^"\']*)["\']', page_source)
            if match_loc:
                print(f"[Bypass] Extracted redirect from page source: {match_loc.group(1)}")
                return match_loc.group(1)
        except Exception:
            pass

        # 8. Check for thenaukriadda 'Go to download'
        try:
            go_download = driver.find_elements(
                By.XPATH,
                "//a[normalize-space(.)='Go to download'] | //a[contains(@href, 'driveseed')] | //a[contains(@href, 'drivedownload')]"
            )
            if go_download:
                href = go_download[0].get_attribute("href")
                if href and any(h in href for h in ["driveseed", "video-seed", "drivedownload"]):
                    print(f"[Bypass] Found 'Go to download' link: {href}")
                    return href
        except Exception:
            pass

        time.sleep(1.0)

    print(f"[Bypass] Timeout reached. Returning current URL: {driver.current_url}")
    return driver.current_url


def process_movie(movie_title, progress_callback=None, auto_select=False, preferred_quality="1080p", headless=False, is_indian=None, download_folder=None, cancel_event=None, on_driver_created=None, tmdb_id=None):
    def check_cancelled():
        if cancel_event and cancel_event.is_set():
            raise KeyboardInterrupt("Scraping cancelled by user")

    print("Scraper received:", movie_title)
    print("Preferred quality:", preferred_quality)
    if is_indian is not None:
        print("Production Origin:", "Bollywood / Indian" if is_indian else "Hollywood / International")
    target_folder = download_folder or DOWNLOAD_FOLDER
    os.makedirs(target_folder, exist_ok=True)
    print("Download Destination:", target_folder)
    if progress_callback:
        progress_callback(0, "0 MB/s", "SEARCHING")

    driver = create_driver(headless=headless, download_folder=target_folder)
    if on_driver_created:
        try:
            on_driver_created(driver)
        except Exception:
            pass

    try:
        check_cancelled()
        movie = movie_title
        results = []

        def generate_search_queries(title):
            queries = []
            no_year = re.sub(r"\s*\(\d{4}\)", "", title).strip()
            clean_punc = re.sub(r"[:\-–—/]", " ", no_year)
            clean_punc = re.sub(r"\s+", " ", clean_punc).strip()
            if clean_punc:
                queries.append(clean_punc)

            year_match = re.search(r"\((\d{4})\)", title)
            main_name = re.split(r"[:\-–—]", no_year)[0].strip()
            main_name = re.sub(r"\s+", " ", main_name).strip()
            if year_match and main_name:
                year = year_match.group(1)
                queries.append(f"{main_name} ({year})")
                queries.append(f"{main_name} {year}")

            if main_name and main_name not in queries:
                queries.append(main_name)

            if no_year not in queries:
                queries.append(no_year)

            return list(dict.fromkeys(queries))

        search_queries = generate_search_queries(movie)

        # Site selection:
        # Bollywood / Indian movies -> MoviesLeech (https://moviesleech.club)
        # Hollywood / International movies -> MoviesMod (https://moviesmod.ai.in)
        if is_indian is True:
            sites_to_try = [
                ("MoviesLeech (Bollywood)", "https://moviesleech.club"),
                ("MoviesMod (Hollywood)", "https://moviesmod.ai.in"),
            ]
        elif is_indian is False:
            sites_to_try = [
                ("MoviesMod (Hollywood)", "https://moviesmod.ai.in"),
                ("MoviesLeech (Bollywood)", "https://moviesleech.club"),
            ]
        else:
            # Auto-detect or search MoviesMod first with fallback to MoviesLeech
            sites_to_try = [
                ("MoviesMod (Hollywood)", "https://moviesmod.ai.in"),
                ("MoviesLeech (Bollywood)", "https://moviesleech.club"),
            ]

        chosen_site_name = ""

        for site_name, base_url in sites_to_try:
            site_matched = False
            for sq in search_queries:
                check_cancelled()
                print(f"Searching on {site_name}: {sq}...")
                encoded_movie = urllib.parse.quote_plus(sq)
                driver.get(f"{base_url}/search/{encoded_movie}")
                try:
                    movie_cards = WebDriverWait(driver, 5).until(
                        EC.presence_of_all_elements_located((By.TAG_NAME, "article"))
                    )
                    site_results = []
                    for card in movie_cards:
                        try:
                            img_el = card.find_elements(By.TAG_NAME, "img")
                            image = img_el[0].get_attribute("src") if img_el else ""
                            movie_link = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                            hero_title = card.find_element(By.TAG_NAME, "h2").text
                            site_results.append({
                                "image": image,
                                "title": hero_title,
                                "link": movie_link,
                            })
                        except Exception:
                            pass

                    if site_results:
                        best_idx, score = find_best_movie_match(site_results, movie_title)
                        if score > 0:
                            results = site_results
                            chosen_site_name = site_name
                            site_matched = True
                            if score > 100:
                                break
                except Exception:
                    continue

            if site_matched and results:
                best_idx, score = find_best_movie_match(results, movie_title)
                if score > 100:
                    break

        if not results:
            print(f"No results found for '{movie_title}' on any platform.")
            return None

        if progress_callback:
            progress_callback(0, "0 MB/s", "FOUND")

        # Automatically determine best movie match based on title and release year
        best_movie_idx, _ = find_best_movie_match(results, movie_title)

        for number, movie_item in enumerate(results, start=1):
            is_rec = (number - 1 == best_movie_idx)
            rec_tag = " [Recommended]" if is_rec else ""
            print(f"{number}. {movie_item['title']}{rec_tag}")

        if auto_select or not results:
            select_movie = best_movie_idx + 1
            print(f"[Auto-selected] Movie: {select_movie}. {results[best_movie_idx]['title']}")
        else:
            try:
                prompt_def = best_movie_idx + 1
                val = input(f"Enter the Movie number (press Enter for recommended {prompt_def}): ").strip()
                select_movie = int(val) if val else prompt_def
            except Exception:
                select_movie = best_movie_idx + 1

        selected_movie = results[select_movie - 1]
        driver.get(selected_movie["link"])

        inside_movie_card = driver.find_element(By.CLASS_NAME, "thecontent")

        # Support both h3 (MoviesLeech) and h4 (MoviesMod) quality headings
        headings = inside_movie_card.find_elements(By.XPATH, ".//*[self::h3 or self::h4]")
        links = []

        for heading in headings:
            heading_text = heading.text.strip()
            if not any(q in heading_text.lower() for q in ["480p", "720p", "1080p", "2160p", "4k", "download"]):
                continue

            try:
                link_el = heading.find_element(
                    By.XPATH,
                    "./following-sibling::p[1]//a | ./following::a[contains(@class, 'maxbutton') or contains(@href, 'archives')][1]"
                )
                href = link_el.get_attribute("href")
                if href and not href.endswith("#"):
                    links.append({
                        "link_title": heading_text,
                        "link": href
                    })
            except Exception:
                pass

        def parse_size_from_title(title):
            """Fallback: extract a size like '[900MB]' or '[1.7GB]' from the title text."""
            match = re.search(r"\[?([\d.]+)\s*(GB|MB)\]?", title, re.IGNORECASE)
            if not match:
                return None
            value, unit = float(match.group(1)), match.group(2).upper()
            return int(value * (1024 ** 3 if unit == "GB" else 1024 ** 2))

        # Automatically determine best quality link based on preferred_quality
        best_link_idx, _ = find_best_quality_link(links, preferred_quality=preferred_quality)

        for number, link_item in enumerate(links, start=1):
            is_rec = (number - 1 == best_link_idx)
            rec_tag = " [Recommended]" if is_rec else ""
            print(f"{number}. {link_item['link_title']}{rec_tag}")

        if auto_select or not links:
            download_link_number = best_link_idx + 1
            print(f"[Auto-selected] Quality ({preferred_quality}): {download_link_number}. {links[best_link_idx]['link_title']}")
        else:
            try:
                prompt_def = best_link_idx + 1
                val = input(f"Enter the download link number (press Enter for recommended {prompt_def}): ").strip()
                download_link_number = int(val) if val else prompt_def
            except Exception:
                download_link_number = best_link_idx + 1

        selected_download_link = links[download_link_number - 1]

        print(f"Navigating to download page: {selected_download_link['link']}")
        driver.get(selected_download_link["link"])
        time.sleep(2)

        # If on modpro.blog, follow the fast server / sid link to the gateway
        cur_url = driver.current_url
        if any(h in cur_url for h in ["modpro.blog", "leechpro.blog", "mflixblog", "archives"]):
            try:
                fast_el = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//a[contains(@class, 'maxbutton-1')] | //a[contains(@class, 'maxbutton')] | //a[contains(@href, 'sid=')]"
                    ))
                )
                fast_server_link = fast_el.get_attribute("href")
                if fast_server_link and fast_server_link != cur_url and not fast_server_link.endswith("#"):
                    print(f"Navigating to gateway: {fast_server_link}")
                    driver.get(fast_server_link)
            except Exception:
                # The injected userscript may have already triggered the navigation
                pass

        # Swiftly bypass link verification gateways (thenaukriadda, unblockedgames, techmny, modpro, etc.)
        driveseed_download_link = bypass_verification_gateways(driver)
        print(f"Bypass complete. Destination link: {driveseed_download_link}")








    # COMMON THING IN THE DRIVESEED / VIDEOSEED LINK RESOLUTION
        if driver.current_url != driveseed_download_link:
            driver.get(driveseed_download_link)

        # 1. DriveSeed file page: find instant / workerseed / video-gen link
        first_url = None
        if "?url=" in driver.current_url or "&url=" in driver.current_url:
            first_url = driver.current_url
        else:
            try:
                driveseed_btn = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//a[contains(@href, 'video-gen')] | //a[contains(@href, 'workerseed')] | //a[contains(@href, 'zfile')] | //a[contains(@class, 'btn-danger')] | //button[contains(@class, 'btn-danger')]"
                    ))
                )
                first_url = driveseed_btn.get_attribute("href")
                print(f"DriveSeed Button Link: {first_url}")
            except Exception as e:
                print(f"Could not find DriveSeed button: {e}")

        url = None

        # Check 1: If first_url already contains ?url=
        if first_url and ("?url=" in first_url or "&url=" in first_url):
            url = first_url.split("url=", 1)[1]

        if not url and first_url:
            # Navigate to video-seed page if not already there
            if driver.current_url != first_url:
                driver.get(first_url)
            time.sleep(1.5)

            # Check 2: If current URL has ?url=
            if "?url=" in driver.current_url or "&url=" in driver.current_url:
                url = driver.current_url.split("url=", 1)[1]
            else:
                # Check 3: Check the download button on video-seed page
                try:
                    d_btn = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//a[@id='ins'] | //a[@id='download'] | //a[contains(@class, 'btn-danger')] | //button[contains(@class, 'btn-danger')] | //a[contains(@class, 'btn')]"
                        ))
                    )
                    outer_url = d_btn.get_attribute("href")
                    print(f"VideoSeed Button Link: {outer_url}")
                    if outer_url and ("?url=" in outer_url or "&url=" in outer_url):
                        url = outer_url.split("url=", 1)[1]
                    elif outer_url and outer_url.startswith("http"):
                        url = outer_url
                except Exception as e:
                    print(f"Could not find VideoSeed button: {e}")

        # Fallback if nothing else matched
        if not url:
            url = driver.current_url

        # Unquote URL-encoded link
        if "%3A" in url or "%2F" in url:
            url = urllib.parse.unquote(url)

        print(f"Final Download Link: {url}")

        # Try to get the real total size via HEAD request (Content-Length header).
        # Falls back to parsing it from the title text (e.g. "[900MB]") if that fails.
        total_size = get_remote_file_size(url)
        if not total_size:
            total_size = parse_size_from_title(selected_download_link['link_title'])
        if total_size:
            print(f"Expected size: {total_size / (1024 * 1024):.1f} MB")
        else:
            print("Could not determine total size - progress bar will show size/speed only.")

        # Clean title for Jellyfin standard naming: replace dots with spaces
        clean_name = re.sub(r'[\\/*?:"<>|]', "", movie_title).strip()
        clean_name = clean_name.replace('.', ' ')
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        if tmdb_id and tmdb_id != "unknown":
            jellyfin_filename = f"{clean_name} [tmdbid-{tmdb_id}]"
        else:
            jellyfin_filename = clean_name

        # 1. Primary: Direct high-speed Python stream download (reliable, immune to headless restrictions)
        try:
            cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in driver.get_cookies())
            download_stream_direct(
                url,
                target_folder,
                default_name=jellyfin_filename,
                total_size=total_size,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
                cookies_str=cookies_str,
            )
            return
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[Downloader] Direct stream download fallback ({e}). Starting browser download...")

        # 2. Fallback: Headless Chromium download
        before_files = set(os.listdir(target_folder))
        driver.get(url)

        wait_for_download(
            target_folder,
            before_files,
            total_size=total_size,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

        if not progress_callback:
            try:
                input("Press Enter to exit...")
            except Exception:
                pass
        # link = inside_card.find_element(By.CLASS_NAME,"maxbutton-1").get_attribute("href")

        # movies_title_and_link = {
        #     "link_title": link_title.text,
        #     "link": link
        # }
        # print(f"Link Title: {link_title.text}")
        # print(f"Link URL: {link}")


    finally:
        try:
            driver.quit()
        except Exception:
            pass
        if hasattr(driver, "_profile_dir") and driver._profile_dir and os.path.exists(driver._profile_dir):
            try:
                shutil.rmtree(driver._profile_dir, ignore_errors=True)
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    test_movie = ""
    if len(sys.argv) > 1:
        test_movie = " ".join(sys.argv[1:]).strip()
    if not test_movie:
        try:
            test_movie = input("Enter movie name to test [Dune (2021)]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nUsing default test movie: Dune (2021)")
            test_movie = ""
    if not test_movie:
        test_movie = "Dune (2021)"
    process_movie(test_movie, auto_select=False, headless=False)
