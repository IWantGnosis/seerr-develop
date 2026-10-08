from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import os
import time
import urllib.request
# from dns_client.adapters.requests import DNSClientSession


# session = DNSClientSession('1.1.1.1')

options = webdriver.ChromeOptions()

options.add_argument("--log-level=3")
# options.add_argument(
#     "--dns-over-https-servers=https://8.8.8.8/dns-query"
# )

DOWNLOAD_FOLDER = r"C:\Users\naksh\Downloads"

prefs = {
    "download.default_directory": DOWNLOAD_FOLDER,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
}

options.add_experimental_option("prefs", prefs)
options.add_experimental_option("excludeSwitches", ["enable-logging"])

service = Service(log_output=os.devnull)

options.binary_location = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

# If you want headless, use the new headless mode (better parity with normal Chrome):
# options.add_argument("--headless=new")
# options.add_argument("--window-size=1920,1080")  # headless defaults to a small viewport

driver = webdriver.Chrome(options=options)

# REQUIRED for downloads to work in headless mode (harmless in normal mode too).
# Headless Chrome blocks file downloads by default unless this CDP command is sent.
driver.execute_cdp_cmd("Page.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": DOWNLOAD_FOLDER
})


def safe_click(driver, element):
    """Scrolls an element to center and clicks it, falling back to a JS click
    if a fixed/sticky element (like the search bar) intercepts the click."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(element))
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


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
                       poll_interval=0.3, stable_checks=3, bar_width=30):
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
        current_files = set(os.listdir(download_folder))
        new_files = current_files - before_files

        # Step 1: find our file (not yet identified)
        if target_path is None:
            # Heartbeat + diagnostics: if nothing new shows up within 8s,
            # print exactly what's in the folder so this never hangs silently.
            waited = time.time() - wait_start
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
        if is_crdownload and not os.path.exists(target_path):
            final_name = os.path.basename(target_path)[: -len(".crdownload")]
            final_path = os.path.join(download_folder, final_name)
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

        if not is_crdownload:
            if current_size == previous_size:
                stable_count += 1
            else:
                stable_count = 0
            if stable_count >= stable_checks:
                if total_size:
                    full_bar = "#" * bar_width
                    print(f"\r[{full_bar}] 100.0% | {current_mb:.1f}/{total_mb:.1f} MB | done"
                          + " " * 20)
                else:
                    full_bar = "#" * bar_width
                    print(f"\r[{full_bar}] {current_mb:.2f} MB | done          ")
                print(f"Download complete: {os.path.basename(target_path)}")
                break

        previous_size = current_size
        previous_time = current_time
        time.sleep(poll_interval)

    return target_path


def process_movie(movie_title):
    print("Scraper received:", movie_title)

    movie = movie_title

    driver.get("https://acermovies.fun/")
    search_box = driver.find_element(By.ID, "searchInput")
    search_box.send_keys(movie)
    search_box.send_keys(Keys.ENTER)

    results = []
    movie_cards = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "#searchResultBox > div.cursor-pointer")
        )
    )

    print("Cards found:", len(movie_cards))
    for card in movie_cards:
        image = card.find_element(By.TAG_NAME, "img").get_attribute("src")
        hero_title = card.find_element(By.TAG_NAME, "span")

        results.append({
            "image": image,
            "title": hero_title.text,
            "hero_title": hero_title
        })

    for number, movie_item in enumerate(results, start=1):
        print(f"{number}.{movie_item['title']}")

    select_movie = int(input("Enter the Movie number: "))
    selected_movie = results[select_movie - 1]

    safe_click(driver, selected_movie['hero_title'])

    download_results = []
    movie_downloads = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "#searchResultBox > div.quality-box")
        )
    )
    for down in movie_downloads:
        download_element = down.find_element(By.TAG_NAME, "a")
        download_title = down.find_element(By.TAG_NAME, "span").text
        download_results.append({
            "element": download_element,
            "title": download_title
        })

    for number, download in enumerate(download_results, start=1):
        print(f"{number}.{download['title']}")

    def parse_size_from_title(title):
        """Fallback: extract a size like '[900MB]' or '[1.7GB]' from the title text."""
        import re
        match = re.search(r"\[?([\d.]+)\s*(GB|MB)\]?", title, re.IGNORECASE)
        if not match:
            return None
        value, unit = float(match.group(1)), match.group(2).upper()
        return int(value * (1024 ** 3 if unit == "GB" else 1024 ** 2))


    selected_download = int(input("Enter the download link number: "))
    selected_download_link = download_results[selected_download - 1]

    link_element = selected_download_link['element']

    # This site needs TWO clicks:
    #   1st click -> populates the real href on the anchor (it starts empty)
    #   2nd click -> fires the actual download
    # We don't rely on knowing exactly WHICH click starts the file on disk -
    # the snapshot is taken before BOTH clicks, so either case is covered.
    before_files = set(os.listdir(DOWNLOAD_FOLDER))

    safe_click(driver, link_element)  # 1st click: reveals href

    WebDriverWait(driver, 10).until(
        lambda d: link_element.get_attribute("href")
        and link_element.get_attribute("href").startswith("http")
    )


    #Final URL of the MOVIE LINK ✅✅✅DOWNLOAD!!!

    url = link_element.get_attribute("href")
    print(f"Download Link: {url}")

    # Try to get the real total size via HEAD request (Content-Length header).
    # Falls back to parsing it from the title text (e.g. "[900MB]") if that fails.
    total_size = get_remote_file_size(url)
    if not total_size:
        total_size = parse_size_from_title(selected_download_link['title'])
    if total_size:
        print(f"Expected size: {total_size / (1024 * 1024):.1f} MB")
    else:
        print("Could not determine total size - progress bar will show size/speed only.")

    safe_click(driver, link_element)  # 2nd click: starts the download

    wait_for_download(DOWNLOAD_FOLDER, before_files, total_size=total_size)

    input("Press Enter to exit...")
    driver.quit()