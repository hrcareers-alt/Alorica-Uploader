import schedule
import time
import pytz
import requests
import gspread
import os
import json
from datetime import datetime

# --- Source Data Links ---
# Main candidate sources[cite: 1]
APPLY_OR_REFER_SHEET = "https://docs.google.com/spreadsheets/d/1NoRX955F0dpxMReiC-6lcd3hgxFDccS3H9hzabTQghE/edit"
DIRECT_SOURCING_SHEET = "https://docs.google.com/spreadsheets/d/12B9N-5AGpWBT8R1ePXBZIwnFmBC7MadIPo5NESUbAuw/edit"
MATIC_APP_SHEET = "https://docs.google.com/spreadsheets/d/1bH5MI6KLsK7OkQefiiLZtpQD3VnjPhdvwgHKkJQSfss/edit"
DIRECT_FORM_SHEET = "https://docs.google.com/spreadsheets/d/1hEblCdSpcpyIWQBXnBx8IQIIdyBTCS-DgmM_nzUJLHc/edit"

# Target Endpoints[cite: 1]
IBEX_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdxw6nizkhs3hUXEj2maOdIw_BhcoGA0SoegKceCIbNo9CppQ/viewform"
ALORICA_FORM_URL = "https://forms.talkpush.com/form/25909c5f-7af0-44e4-8a58-64ecfbb9dc5f"

# Initialize Google Sheets client
try:
    # Attempt to load from Cursor environment secret first
    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_env:
        creds_dict = json.loads(creds_env)
        gc = gspread.service_account_from_dict(creds_dict)
        print("Authenticated using Cursor secret.")
    else:
        # Fallback for local testing
        gc = gspread.service_account(filename='credentials.json')
        print("Authenticated using local credentials.json.")
except Exception as e:
    print(f"Failed to authenticate Google Sheets client: {e}")
    gc = None

def acquire_lock(lock_file):
    """Ensures two bots never run the same job at once[cite: 1]."""
    if os.path.exists(lock_file):
        return False
    # Ensure directory exists
    os.makedirs(os.path.dirname(lock_file), exist_ok=True)
    with open(lock_file, 'w') as f:
        f.write(str(time.time()))
    return True

def release_lock(lock_file):
    if os.path.exists(lock_file):
        os.remove(lock_file)

def run_ibex_job():
    lock_file = "/workspace/uploader/locks/ibex.lock"
    if not acquire_lock(lock_file):
        print("IBEX job is already running.")
        return

    try:
        print("Executing IBEX Job...")
        if not gc:
            print("Google client missing. Aborting IBEX run.")
            return

        # Connecting to the main sheet
        main_sheet = gc.open_by_url(APPLY_OR_REFER_SHEET)
        modern_traction_tab = main_sheet.worksheet("MODERN TRACTION")
        
        # Rule: Only rows whose IBEX remark cell (Column Z for MODERN TRACTION) is blank get processed[cite: 1].
        # Rule: At most 150 DIRECT SOURCING sends per run[cite: 1].
        
        # Fixed Payload Data for IBEX[cite: 1]
        ibex_base_payload = {
            "entry.xxxx": "I agree and give my consent", 
            "entry.xxxx": "BHL-XTRA-178",                
            "entry.xxxx": "Edward Belacse",              
            "entry.xxxx": "9422642828",                  
            "entry.xxxx": "Virtual Express Lobby (VEL)"  
        }
        
        # TODO: Read rows, format mobile to 10 digits starting with 9, calculate closest site, and POST[cite: 1].
        # TODO: Re-read remark cell right before writing. Never overwrite a filled cell[cite: 1].
        # TODO: Write back "Executive Team", "Duplicate", "Incomplete (Issue)", or "INVALID"[cite: 1].

    finally:
        release_lock(lock_file)

def run_alorica_job():
    lock_file = "/workspace/uploader/locks/alorica.lock"
    if not acquire_lock(lock_file):
        print("Alorica job is already running.")
        return

    try:
        print("Executing Alorica Job...")
        if not gc:
            print("Google client missing. Aborting Alorica run.")
            return

        # Rule: Keep last handled rows in a local JSON state file[cite: 1].
        state_file = "/workspace/uploader/state/alorica_tails.json"
        
        # Fixed Payload Data for Alorica Talkpush[cite: 1]
        alorica_base_payload = {
            "referrer": "Edward Belacse - Olympuz",
            "community": "Community Referrer from Barangay",
            "city": "Cebu City"
        }
        
        # TODO: Read rows up to 199 rows behind the last handled row for each tab[cite: 1].
        # TODO: Fix email typos (e.g., .con to .com), format phone as '+63 9XXXXXXXXX'[cite: 1].
        # TODO: Calculate nearest Alorica site (never ABB), default missing location to 'Cebu'[cite: 1].
        # TODO: POST to Talkpush and write back "Executive Team", "Existing Application", "Duplicate", etc.[cite: 1].

    finally:
        release_lock(lock_file)

def main():
    # Both jobs run every hour, 8 AM to 1 AM PHT[cite: 1].
    # IBEX runs at :09 and Alorica at :39[cite: 1].
    schedule.every().hour.at(":09").do(run_ibex_job)
    schedule.every().hour.at(":39").do(run_alorica_job)

    print("Agent Initialized. Scheduled jobs configured.")

    while True:
        manila_tz = pytz.timezone('Asia/Manila')
        current_hour = datetime.now(manila_tz).hour
        
        # Jobs run between 8 AM and 1 AM PHT[cite: 1].
        if 8 <= current_hour <= 23 or current_hour == 0:
            schedule.run_pending()
        
        time.sleep(30)

if __name__ == "__main__":
    main()
