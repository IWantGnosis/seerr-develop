from selenium import webdriver
from selenium_stealth import stealth

options = webdriver.ChromeOptions()

options.add_argument("--log-level=3")
options.add_experimental_option(
    "excludeSwitches",
    ["enable-logging"]
)

options.binary_location = (
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
)

driver = webdriver.Chrome(options=options)

stealth(
    driver,
    languages=["en-US", "en"],
    vendor="Google Inc.",
    platform="Win32",
    webgl_vendor="Intel Inc.",
    renderer="Intel Iris OpenGL Engine",
    fix_hairline=True,
)

driver = webdriver.Chrome(options=options)


driver.get("https://filemood.com/")

input("Press Enter after solving the CAPTCHA and logging in to ext2.to...")

driver.quit()