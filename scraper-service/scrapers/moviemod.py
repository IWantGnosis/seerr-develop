from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import os
import re
import time
import urllib.request
from urllib.parse import urlparse, parse_qs


# import time
options = webdriver.ChromeOptions()
options.add_argument("--log-level=3")


DOWNLOAD_FOLDER = r"C:\Users\naksh\Downloads"

prefs = {
    "download.default_directory": DOWNLOAD_FOLDER,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
}

# Disable Chrome logging to console
options.add_experimental_option(
    "excludeSwitches",
    ["enable-logging"]
)

# Silence ChromeDriver logs
service = Service(log_output=os.devnull)
# options.add_extension(
#     r"C:\Users\naksh\Downloads\torrent-notify\extension\uBlock.crx"
# )
# options.add_extension("Extension/ublock.crx")

options.binary_location = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

# # If you want headless, use the new headless mode (better parity with normal Chrome):
# options.add_argument("--headless=new")
# options.add_argument("--window-size=1920,1080")  # headless defaults to a small viewport

driver = webdriver.Chrome(options=options)

# REQUIRED for downloads to work in headless mode (harmless in normal mode too).
# Headless Chrome blocks file downloads by default unless this CDP command is sent.
driver.execute_cdp_cmd("Page.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": DOWNLOAD_FOLDER
})




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












#This is my Code i written with the help of chatgpt to learns some stuff but it was helpfull


# def process_movie(movie_title):
#     print("Scraper received:", movie_title)

#     movie = movie_title


movie = input("Enter the movie name: ")
results = []

encoded_movie = urllib.parse.quote_plus(movie)
driver.get(f"https://moviesmod.ai.in/search/{encoded_movie}")
# download shit not configured i want to put the class based on the website
# driver.get(f"https://moviesleech.club/search/{encoded_movie}") 

# search_box = driver.find_element(By.ID,"s")
# search_box = WebDriverWait(driver,15).until(EC.presence_of_element_located((By.ID,"s")))
# search_box.send_keys(movie)#
# search_box.send_keys(Keys.ENTER)


movie_cards =  WebDriverWait(driver,10).until(EC.presence_of_all_elements_located((By.TAG_NAME, "article")))

for card in movie_cards:
    image = card.find_element(By.TAG_NAME,"img").get_attribute("src")
    # image_url = image.get_attribute("src")
    movie_link = card.find_element(By.TAG_NAME,"a").get_attribute("href")
    hero_title = card.find_element(By.TAG_NAME,"h2")

    movies = {
        
        "image": image,
        "title": hero_title.text,
        "link": movie_link,
        # "element": hero_title
    }
    results.append(movies)

for number, movie in enumerate(results,start= 1):
    print(f"{number}.{movie['title']}")



# print(results)
select_movie = int(input("Enter the Movie number: "))
selected_movie = results[select_movie - 1]

driver.get(selected_movie["link"])
# print(selected_movie)

# print(movie.selected_movie[hero_title])

inside_movie_card = driver.find_element(By.CLASS_NAME,"thecontent")
# print(len(inside_movie_card))



titles = inside_movie_card.find_elements(By.TAG_NAME, "h4")
links=[]

for title in titles:
    link = title.find_element(
        By.XPATH,
        "./following-sibling::p[1]/a"
    )

    download_links = {
        "link_title": title.text,
        "link": link.get_attribute("href")
    }
    links.append(download_links)
    # print(f"Title: {title.text}")
    # print(f"Link: {link.get_attribute('href')}")

for number, link in enumerate(links,start=1):
    print(f"{number}.{link['link_title']}")

def parse_size_from_title(title):
    """Fallback: extract a size like '[900MB]' or '[1.7GB]' from the title text."""
    import re
    match = re.search(r"\[?([\d.]+)\s*(GB|MB)\]?", title, re.IGNORECASE)
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2).upper()
    return int(value * (1024 ** 3 if unit == "GB" else 1024 ** 2))



download_link_number = int(input("Enter the download link number: "))
selected_download_link = links[download_link_number - 1]

driver.get(selected_download_link["link"])

fast_server_element = WebDriverWait(driver,15).until(EC.presence_of_element_located((By.CLASS_NAME,"maxbutton-1")))
fast_server_link = fast_server_element.get_attribute("href")

driver.get(fast_server_link)

# cloud_start_verify = driver.find_element(By.CSS_SELECTOR,"span.block a")
cloud_start_verify = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((
        By.XPATH,
        "//button[normalize-space(.)='Click here to continue']"
    ))
)

cloud_start_verify.click()

# <a id="two_steps_btn" class="block cursor-pointer max-w-xs mx-auto my-0 bg-blue-500 text-white px-6 py-2 shadow my-6 transform hover:scale-95 transition-transform text-center uppercase " style="color:white !important; text-decoration: none !important;" target="_blank" rel="nofollow">Generating Links ...</a>

# <a id="two_steps_btn" class="block cursor-pointer max-w-xs mx-auto my-0 bg-blue-500 text-white px-6 py-2 shadow my-6 transform hover:scale-95 transition-transform text-center uppercase" style="color:white !important; text-decoration: none !important;" target="_blank" rel="nofollow" href="https://cloud.unblockedgames.world/?go=pepe-6a9c30bb01436">Go to download</a>



# 1. Locate the script tag containing the code
# If there are multiple script tags, use an index or partial text match
# script_element = WebDriverWait(driver,15).until(EC.presence_of_element_located((By.XPATH, "//script[contains(text(), 'c.setAttribute')]")))

# # 2. Get the full text/code inside the script tag
# script_code = script_element.get_attribute("innerHTML")

# # 3. Use Regex to find the URL inside c.setAttribute("href", "...")
# match = re.search(r'c\.setAttribute\("href",\s*"(https?://[^"]+)"\)', script_code)

# if match:
#     driveseed_download_link = match.group(1)
#     print(f"Extracted Link: {driveseed_download_link}")
# else:
#     print("Link not found in the script tag.")


continue_button = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((
        By.XPATH,
        "//button[normalize-space(.)='Click here to continue']"
    ))
)

driver.execute_script(
    "arguments[0].click();",
    continue_button
)

driveseed_download_link = WebDriverWait(driver, 10).until(
    lambda d: (
        d.find_element(
            By.XPATH,
            "//a[normalize-space(.)='Go to download']"
        ).get_attribute("href")
        or None
    )
)

print("Extracted Link:", driveseed_download_link)

# const i=document.getElementById("verify_button"),a=document.getElementById("verify_text"),c=document.getElementById("two_steps_btn"),d=document.getElementById("verify_button2");var isCompleted;function s_343(e,t,n){const d=new Date;d.setTime(d.getTime()+60*n*1e3);n="expires="+d.toUTCString();document.cookie=e+"="+t+";"+n+";path=/"}d.addEventListener("click",()=>{var e=9;d.classList.add("hidden"),a.classList.remove("hidden");var t=setInterval(function(){document.getElementById("verify_text").innerHTML="Please Wait "+--e+" Seconds",e<=0&&(document.getElementById("verify_button").classList.remove("hidden"),document.getElementById("verify_text").classList.add("hidden"),clearInterval(t))},1e3)}),i.addEventListener("click",()=>{if(c.classList.add("block"),c.classList.remove("hidden"),window.scrollTo({top:c.offsetTop,behavior:"smooth"}),isCompleted)return!1;let e=0;Math.floor(1e4*Math.random()),Math.floor(1e4*Math.random());const t=setInterval(()=>{isCompleted=!0,1===e&&(c.innerText="Checking Request ..."),3===e&&(c.innerText="Sending Response ..."),5===e&&(c.innerText="Generating Links ..."),6===e&&(c.innerText="Go to download",c.setAttribute("href","https://cloud.unblockedgames.world/?go=pepe-6a9c30bb01436"),clearInterval(t)),e+=1},1e3)});
#     s_343('pepe-6a9c30bb01436', 'eJwFwUtygyAAANArCWhnusgiRki0Sgfko+wUnFDFaPOZWE/f9zrUxt0+oVqYhKvV98BGLlqnIQuhH8NLRbQWGW+oDt/1XBiRkVQC/q7Q8S1wUfcX/xhGU9qZtmwnD3VWkE1bJef14SQ3HHlG8ZJYeIXy4pdK85TOT+g0243ekBklcJMXApG/mhReREngurj3wFxkxOP2xjMDQzngAAx2GUcrkcAsJfQFJ2HRmJwqlEMtVyxE+C1BeuI3vBmVv6neIivCJoDbmFR/VmLopMt1sz7t2SatLhI6T5saA68ViU1o95qopsPXuAvpVwvt7lT6w+BnzCYfDaPzAvq0g+ZlG/+hz/ndTslJzgnjU2AUGdXrN3LHw+EfcbBykg==', 60);


driver.get(driveseed_download_link)

driveseed_instant_d = WebDriverWait(driver,15).until(EC.presence_of_element_located((By.CLASS_NAME,"btn-danger")))
driver.get(driveseed_instant_d.get_attribute("href"))

d_link = WebDriverWait(driver,15).until(EC.presence_of_element_located((By.CLASS_NAME,"btn-danger")))
# url = d_link.get_attribute("href")
outer_url = d_link.get_attribute("href")

url = parse_qs(
    urlparse(outer_url).query
)["url"][0]

# print("Final URL:", inner_url)

print(f"Final Download Link: {url}")

before_files = set(os.listdir(DOWNLOAD_FOLDER))
driver.get(url)

#Final URL of the MOVIE LINK ✅✅✅DOWNLOAD!!!
# d_link.click()  # Click the download button to start the download



# Try to get the real total size via HEAD request (Content-Length header).
# Falls back to parsing it from the title text (e.g. "[900MB]") if that fails.
total_size = get_remote_file_size(url)
if not total_size:
    total_size = parse_size_from_title(selected_download_link['link_title'])
if total_size:
    print(f"Expected size: {total_size / (1024 * 1024):.1f} MB")
else:
    print("Could not determine total size - progress bar will show size/speed only.")


wait_for_download(DOWNLOAD_FOLDER, before_files, total_size=total_size)







input("Press Enter to exit...")
# link = inside_card.find_element(By.CLASS_NAME,"maxbutton-1").get_attribute("href")

# movies_title_and_link = {
#     "link_title": link_title.text,
#     "link": link
# }
# print(f"Link Title: {link_title.text}")
# print(f"Link URL: {link}")
driver.quit()