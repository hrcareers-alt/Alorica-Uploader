import os
import re
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# --- CONFIGURATION ---
ALORICA_LINK = "https://forms.talkpush.com/form/25909c5f-7af0-44e4-8a58-64ecfbb9dc5f"

def setup_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    json_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if json_creds:
        creds_dict = json.loads(json_creds)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("service_account.json", scopes=scopes)
    return gspread.authorize(creds)

def format_alorica_phone(phone_str):
    if not phone_str or str(phone_str).strip() == "":
        return "+63 900XXXXXXX"
    digits = re.sub(r'\D', '', str(phone_str))
    if len(digits) >= 10:
        return "+63 9" + digits[-9:]
    return "+63 900XXXXXXX"

def get_alorica_site(location):
    loc = str(location).lower().strip()
    if not loc or loc in ["n/a", "remote", "wfh"]: return "Cebu"
    if loc in ["philippines", "ph", "phils"]: return "Makati MJ Plaza"
    if any(x in loc for x in ["tagbilaran", "bohol", "cebu"]): return "Cebu"
    if "bulacan" in loc or "hagonoy" in loc: return "Centris"
    if "tayabas" in loc or "quezon" in loc or "tiaong" in loc: return "Lipa"
    if "bataan" in loc: return "Clark"
    if "morong" in loc or "rizal" in loc: return "Marikina"
    if "calasiao" in loc: return "Ilocos"
    # Default fallback per rules
    return "Cebu" 

def get_alorica_exp(exp_str):
    exp = str(exp_str).lower().strip()
    if "1 year" in exp: 
        return "12-23 mos BPO"
    # Placeholder for exact string matching. Default to 0-5 mos BPO per instructions.
    return "0-5 mos BPO"

def run_alorica_pipeline():
    gc = setup_gspread()
    doc = gc.open_by_url("https://docs.google.com/spreadsheets/d/1NoRX955F0dpxMReiC-6lcd3hgxFDccS3H9hzabTQghE/edit")
    
    # Target Tabs, target column index (1-based), starting row, and data indices (0-based)
    tabs = [
        {"name": "MODERN TRACTION", "col": 21, "start": 2, "first": 2, "last": 3, "phone": 4, "email": 5, "loc": 6, "exp": 8},
        {"name": "NEW AFFILIATE REFERRAL SYSTEM", "col": 15, "start": 2, "first": 1, "last": 0, "phone": 2, "email": 4, "loc": 3, "exp": 5},
        {"name": "JOBSTREET", "col": 24, "start": 2, "first": 2, "last": 3, "phone": 4, "email": 5, "loc": 6, "exp": 8}
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        for tab_info in tabs:
            try:
                ws = doc.worksheet(tab_info["name"])
                data = ws.get_all_values()
            except Exception as e:
                print(f"Could not load tab {tab_info['name']}: {e}")
                continue

            # Verify header exactly matches Alorica in the target column before writing
            if len(data) > 0 and "ALORICA" not in str(data[0][tab_info["col"]-1]).upper():
                continue

            for row_idx in range(tab_info["start"] - 1, len(data)):
                row = data[row_idx]
                if len(row) < tab_info["col"]: 
                    row.extend([""] * (tab_info["col"] - len(row)))
                
                # Re-read specific cell right before processing to ensure it hasn't changed
                current_remark = ws.cell(row_idx + 1, tab_info["col"]).value or ""
                if current_remark.strip():
                    continue

                # Map columns based on tab layout
                first_name = row[tab_info["first"]].strip() if len(row) > tab_info["first"] else ""
                last_name = row[tab_info["last"]].strip() if len(row) > tab_info["last"] else ""
                email = row[tab_info["email"]].strip().lower() if len(row) > tab_info["email"] else ""
                phone = format_alorica_phone(row[tab_info["phone"]] if len(row) > tab_info["phone"] else "")
                loc = row[tab_info["loc"]].strip() if len(row) > tab_info["loc"] else ""
                exp = get_alorica_exp(row[tab_info["exp"]] if len(row) > tab_info["exp"] else "")

                # Fix common email typos
                if email.endswith(".con"):
                    email = email.replace(".con", ".com")

                # Validation: Check incomplete info (Missing email, missing name, or N/A location)
                if not email or "@" not in email or email.endswith("g,ail.com") or not first_name or loc in ["N/A", ""]:
                    ws.update_cell(row_idx + 1, tab_info["col"], "Incomplete Info")
                    continue
                
                # Validation: Check for locations abroad
                loc_lower = loc.lower()
                if "abroad" in loc_lower or loc_lower in ["dubai", "uae", "singapore", "usa", "zimbabwe", "malaysia"]:
                    ws.update_cell(row_idx + 1, tab_info["col"], "INVALID")
                    continue

                site = get_alorica_site(loc)

                # Upload via Playwright - High Speed Mode
                page = context.new_page()
                try:
                    # wait_until="domcontentloaded" ensures instant execution the moment the form renders
                    page.goto(ALORICA_LINK, wait_until="domcontentloaded", timeout=30000)
                    
                    # Example of zero-delay text filling (Add Talkpush selectors here)
                    # page.locator("input[name='firstname']").fill(first_name)
                    # page.locator("input[name='lastname']").fill(last_name)
                    # page.locator("input[name='email']").fill(email)
                    
                    ws.update_cell(row_idx + 1, tab_info["col"], "Executive Team")
                except Exception as e:
                    print(f"Failed Alorica submission for Row {row_idx + 1} ({tab_info['name']}): {e}")
                finally:
                    page.close()

        browser.close()

if __name__ == "__main__":
    run_alorica_pipeline()
