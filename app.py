import os
import glob
import time
import openai
from openai import OpenAI
import PyPDF2
import pytesseract
import ast
import pandas as pd
from pdf2image import convert_from_path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# === Configuration ===
DOWNLOAD_DIR = "/Users/walidmaaninou/Downloads"
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_API_KEY)

# === Streamlit App Setup ===
st.set_page_config(page_title="📄 Address Extractor", layout="wide")
st.title("📥 Virginia Land Records OCR Extractor")

if "results" not in st.session_state:
    st.session_state["results"] = []
if "scraping" not in st.session_state:
    st.session_state["scraping"] = False

results_placeholder = st.empty()

# === Address Extraction Logic ===
def extract_addresses_from_pdf(filepath):
    print(f"🧾 Starting OCR for file: {filepath}")
    try:
        images = convert_from_path(filepath)
        full_text = ""
        for i, img in enumerate(images):
            page_text = pytesseract.image_to_string(img)
            full_text += f"--- Page {i+1} ---\n{page_text.strip()}\n\n"
        print("✅ OCR completed successfully.")
    except Exception as e:
        print(f"❌ OCR failed: {e}")
        return [f"OCR failed: {e}"]

    if not full_text.strip():
        print("⚠️ No text detected in PDF.")
        return ["⚠️ No text detected in PDF."]

    prompt = f"""
From the text below, extract the **single most likely physical mailing address** (property address).
Output only a **Python list containing one string**, with no explanation:

\"\"\"{full_text[:3000]}\"\"\"
"""

    try:
        print("🔗 Sending text to OpenAI for address extraction...")
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        result = response.choices[0].message.content
        addresses = ast.literal_eval(result.strip())
        print(f"✅ Extracted addresses: {addresses}")
        return addresses
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return [f"OpenAI error: {e}"]

# === Selenium Helpers ===
def wait_for_new_pdf(before_files):
    print("⏳ Waiting for PDF download...")
    timeout = 30
    for _ in range(timeout):
        current_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.pdf"))
        new_files = list(set(current_files) - set(before_files))
        if new_files:
            print(f"✅ New PDF downloaded: {new_files[0]}")
            return new_files[0]
        time.sleep(1)
    raise TimeoutError("No PDF downloaded.")

def process_row(row_element, wait, driver):
    print("⚙️ Processing row...")
    before_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.pdf"))
    driver.execute_script("window.scrollTo(0, 0);")
    row_element.click()
    time.sleep(1)
    try:
        tools_btn = wait.until(EC.element_to_be_clickable((By.ID, 'secondaryToolbarToggle')))
        time.sleep(2)
        tools_btn.click()
        time.sleep(1)
        download_btn = wait.until(EC.element_to_be_clickable((By.ID, "secondaryDownload")))
        driver.execute_script("arguments[0].click();", download_btn)

        filepath = wait_for_new_pdf(before_files)
        addresses = extract_addresses_from_pdf(filepath)

        for addr in addresses:
            st.session_state["results"].append({
                "Filename": os.path.basename(filepath),
                "Extracted Address": addr
            })
            results_placeholder.dataframe(pd.DataFrame(st.session_state["results"]).drop_duplicates())

    except Exception as e:
        print(f"❌ Download/OCR failed: {e}")

    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Go Back')]"))).click()
    time.sleep(1)

# === Scraping Routine ===
def start_scraping():
    st.session_state["scraping"] = True
    print("🚀 Starting scraping session...")
    options = Options()
    options.add_argument("--headless=new")  # Enables headless mode using the new headless implementation

    options.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    })
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)

    # === Login Sequence ===
    try:
        driver.get("https://risweb.vacourts.gov/jsra/sra/#/login")
        wait.until(EC.presence_of_element_located((By.NAME, "email"))).send_keys("brandonle@non-stopinvestments.com")
        wait.until(EC.presence_of_element_located((By.NAME, "password"))).send_keys("Jarvis!23")
        checkbox = driver.find_element(By.NAME, "termsCheck")
        if not checkbox.is_selected():
            checkbox.click()
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Login']"))).click()
        print("🔐 Logged in.")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return

    # === Search Form Sequence ===
    driver.get("https://risweb.vacourts.gov/jsra/sra/#/search/recordSearch")
    wait.until(EC.element_to_be_clickable((By.XPATH, "//td[normalize-space(text())='Norfolk City']"))).click()
    wait.until(EC.element_to_be_clickable((By.XPATH, "//td[normalize-space(text())='Deeds and Land Records']"))).click()

    wait.until(EC.presence_of_element_located((By.ID, "search-name-input"))).send_keys("aa")
    today = datetime.today()
    from_date = (today - timedelta(days=90)).strftime("%m/%d/%Y")
    to_date = today.strftime("%m/%d/%Y")

    # --- Set "From Date" ---
    from_input = wait.until(
        EC.presence_of_element_located((By.XPATH, "//div[@id='search-from-calendar']//input[@type='text']"))
    )
    from_input.clear()
    time.sleep(0.5)
    from_input.click()
    time.sleep(0.5)
    from_input.send_keys(from_date)



    # --- Set "To Date" ---
    to_input = wait.until(
        EC.presence_of_element_located((By.XPATH, "//div[@id='search-to-calendar']//input[@type='text']"))
    )
    to_input.clear()
    time.sleep(0.5)
    to_input.click()
    time.sleep(0.5)
    to_input.send_keys(to_date)

    options_list = [
        "AFFIDAVIT", "DEED TRANSFER ON DEATH", "DEED PURSUANT TO DIVORCE", "DIVORCE DECREE",
        "MECHANICS LIEN", "MEMORANDUM OF LIEN", "NOTICE OF LIEN", "NOTICE OF LIS PENDENS",
        "NOTICE", "ORDER-DECREE BANKRUPTCY W/PLAT", "REAL ESTATE AFFIDAVIT", "WILL"
    ]
    dropdown = wait.until(EC.presence_of_element_located((By.XPATH, "//label[text()='Instrument Type']/following-sibling::div")))
    dropdown.click()
    search_input = dropdown.find_element(By.TAG_NAME, "input")
    for item in options_list:
        search_input.clear()
        search_input.send_keys(item)
        time.sleep(0.5)
        search_input.send_keys(Keys.ENTER)
    time.sleep(1)
    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Search']"))).click()
    time.sleep(3)

    # === Row Processing Loop ===
    row_index = 0
    while st.session_state["scraping"]:
        try:
            rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#court_fips_table tbody tr")))
            if row_index >= len(rows):
                break
            print(f"➡️ Processing row {row_index+1} of {len(rows)}...")
            process_row(rows[row_index], wait, driver)
            row_index += 1
        except Exception as e:
            print(f"❌ Error at row {row_index}: {e}")
            break

    driver.quit()
    st.session_state["scraping"] = False
    print("✅ Scraping completed.")

# === Streamlit UI ===
if st.button("🚀 Start Scraping"):
    start_scraping()

if st.session_state["scraping"]:
    st_autorefresh(interval=3000, key="auto-refresh")

if st.session_state["results"]:
    df = pd.DataFrame(st.session_state["results"]).drop_duplicates()
    results_placeholder.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Results as CSV", csv, "extracted_addresses.csv", "text/csv")
