'''
Author:     Shubham
LinkedIn:   https://www.linkedin.com/in/shubham-sunil-kumar-333547133/

License:    GNU Affero General Public License
            https://www.gnu.org/licenses/agpl-3.0.en.html

GitHub:     https://github.com/theturkishangorashiro-art/apply-and-pray

Support me: https://github.com/sponsors/theturkishangorashiro-art
'''

from modules.helpers import get_default_temp_profile, make_directories
import os
import sys
import re
import shutil
import subprocess
from config.settings import run_in_background, stealth_mode, disable_extensions, safe_mode, file_name, failed_file_name, logs_folder_path, generated_resume_path
from config.questions import default_resume_path
if stealth_mode:
    import undetected_chromedriver as uc
else: 
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    # from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from modules.helpers import find_default_profile_directory, critical_error_log, print_lg
from selenium.common.exceptions import SessionNotCreatedException


def get_installed_chrome_major_version() -> int | None:
    """Detects installed Google Chrome major version."""
    commands: list[list[str]] = []
    if os.name == "nt":
        commands.extend([
            [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--version"],
            [r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "--version"],
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-Item 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe').VersionInfo.ProductVersion",
            ],
            ["reg", "query", r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon", "/v", "version"],
            ["reg", "query", r"HKEY_LOCAL_MACHINE\Software\Google\Chrome\BLBeacon", "/v", "version"],
        ])
    elif sys.platform == "darwin":
        commands.append(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"])
    else:
        commands.extend([["google-chrome", "--version"], ["google-chrome-stable", "--version"], ["chromium", "--version"], ["chromium-browser", "--version"]])
    for command in commands:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=5)
            output = (completed.stdout or completed.stderr or "").strip()
            match = re.search(r"(\d+)\.\d+\.\d+\.\d+", output)
            if match: return int(match.group(1))
        except Exception:
            continue
    return None

def _saved_driver_path(chrome_major: int) -> str:
    '''Our own copy of the patched ChromeDriver for this Chrome version (undetected_chromedriver deletes and re-downloads its own every run).'''
    return os.path.join(uc.Patcher.data_path, f"apply_and_pray_chromedriver_{chrome_major}" + (".exe" if os.name == "nt" else ""))


def create_undetected_chrome(make_options):
    '''
    Starts Chrome in undetected mode. `make_options()` returns new ChromeOptions (undetected_chromedriver can't use one twice).
    Reuses the ChromeDriver kept by an earlier run for the same Chrome version, so a run starts even without internet;
    a download is only needed once per Chrome version.
    '''
    chrome_major = get_installed_chrome_major_version()
    if not chrome_major:
        print_lg("Could not detect Chrome version automatically. Downloading ChromeDriver with its default detection...")
        return uc.Chrome(options=make_options())
    print_lg(f"Detected Chrome major version: {chrome_major}. Using matching ChromeDriver.")
    saved = _saved_driver_path(chrome_major)
    if os.path.exists(saved):
        try: return uc.Chrome(options=make_options(), version_main=chrome_major, driver_executable_path=saved)
        except Exception as e:
            print_lg(f"The saved ChromeDriver didn't start ({str(e).splitlines()[0][:150]}), downloading a new one.")
            try: os.remove(saved)
            except OSError: pass
    print_lg("Downloading ChromeDriver... (only once per Chrome version)")
    driver = uc.Chrome(options=make_options(), version_main=chrome_major)
    try: shutil.copy2(driver.patcher.executable_path, saved)
    except Exception as e: print_lg("Couldn't keep a copy of ChromeDriver for next time:", e)
    return driver


def is_network_error(error: Exception) -> bool:
    '''True when ChromeDriver couldn't be downloaded because the internet / DNS is down.'''
    text = f"{type(error).__name__} {error}".lower()
    return any(word in text for word in ("getaddrinfo", "urlopen error", "urlerror", "name resolution", "connection refused", "connection reset", "network is unreachable"))

def createChromeSession(isRetry: bool = False):
    make_directories([file_name,failed_file_name,logs_folder_path+"/screenshots",default_resume_path,generated_resume_path+"/temp"])
    # Set up WebDriver with Chrome Profile
    print_lg("IF YOU HAVE MORE THAN 10 TABS OPENED, PLEASE CLOSE OR BOOKMARK THEM! Or it's highly likely that application will just open browser and not do anything!")
    profile_dir = find_default_profile_directory()
    if isRetry:
        print_lg("Will login with a guest profile, browsing history will not be saved in the browser!")
    elif not (profile_dir and not safe_mode):
        print_lg("Logging in with a guest profile, Web history will not be saved!")
    def make_options():
        options = uc.ChromeOptions() if stealth_mode else Options()
        if run_in_background:   options.add_argument("--headless")
        if disable_extensions:  options.add_argument("--disable-extensions")
        if isRetry: pass
        elif profile_dir and not safe_mode: options.add_argument(f"--user-data-dir={profile_dir}")
        else: options.add_argument(f"--user-data-dir={get_default_temp_profile()}")
        return options
    options = None
    if stealth_mode: driver = create_undetected_chrome(make_options)
    else: driver = webdriver.Chrome(options=(options := make_options()))
    driver.maximize_window()
    wait = WebDriverWait(driver, 5)
    actions = ActionChains(driver)
    return options, driver, actions, wait

try:
    options, driver, actions, wait = None, None, None, None
    options, driver, actions, wait = createChromeSession()
except SessionNotCreatedException as e:
    critical_error_log("Failed to create Chrome Session, retrying with guest profile", e)
    options, driver, actions, wait = createChromeSession(True)
except Exception as e:
    msg = 'Seems like Google Chrome is out dated. Update browser and try again! \n\n\nIf issue persists, try Safe Mode. Set, safe_mode = True in config.py \n\nPlease check GitHub discussions/support for solutions https://github.com/theturkishangorashiro-art/apply-and-pray \n                                   OR \nReach out through the GitHub repository support channels.'
    if isinstance(e,TimeoutError): msg = "Couldn't download Chrome-driver. Set stealth_mode = False in config!"
    if is_network_error(e): msg = "No internet connection: ChromeDriver (the part that lets the bot control Chrome) couldn't be downloaded.\n\nCheck your Wi-Fi / internet and run the bot again. Chrome itself is fine, you don't need to update it.\n\n(ChromeDriver is downloaded once per Chrome version, then reused.)"
    print_lg(msg)
    critical_error_log("In Opening Chrome", e)
    from pyautogui import alert
    alert(msg, "Error in opening chrome")
    try: driver.quit()
    except NameError: exit()
    
