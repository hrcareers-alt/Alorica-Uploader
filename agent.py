import schedule
import time
import pytz
import requests
from datetime import datetime

# --- Source Data Links ---
# The primary data sources for candidate details[cite: 1]
APPLY_OR_REFER_SHEET = "https://docs.google.com/spreadsheets/d/1NoRX955F0dpxMReiC-6lcd3hgxFDccS3H9hzabTQghE/edit"
DIRECT_SOURCING_SHEET = "https://docs.google.com/spreadsheets/d/12B9N-5AGpWBT8R1ePXBZIwnFmBC7MadIPo5NESUbAuw/edit"
MATIC_APP_SHEET = "https://docs.google.com/spreadsheets/d/1bH5MI6KLsK7OkQefiiLZtpQD3VnjPhdvwgHKkJQSfss/edit"
DIRECT_FORM_SHEET = "https://docs.google.com/spreadsheets/d/1hEblCdSpcpyIWQBXnBx8IQIIdyBTCS-DgmM_nzUJLHc/edit"

# --- Target Endpoints ---
# The destinations where candidate profiles are uploaded[cite: 1]
IBEX_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdxw6nizkhs3hUXEj2maOdIw_BhcoGA0SoegKceCIbNo9CppQ/viewform"
ALORICA_FORM_URL = "https://forms.talkpush.com/form/25909c5f-7af0-44e4-8a58-64ecfbb9dc5f"

def run_ibex_job():
    """
    Executes the IBEX submission job.
    Key parameters to implement:
    - Limit to 150 DIRECT SOURCING sends per run[cite: 1].
    - Send external referrer details: XID BHL-XTRA-178, Full Name Edward Belacse, Mobile 9422642828[cite: 1].
    - Filter rows where the IBEX remark cell is blank, and skip if location is outside the Philippines[cite: 1].
    """
    print("Executing IBEX Job...")
    # TODO: Implement gspread authentication and data parsing logic here.
    # TODO: Implement requests.post() to IBEX_FORM_URL and verify "Your response has been recorded"[cite: 1].

def run_alorica_job():
    """
    Executes the Alorica submission job.
    Key parameters to implement:
    - Referrer must be set to 'Edward Belacse - Olympuz'[cite: 1].
    - Scan up to 199 rows behind the last handled row to find blank remark cells[cite: 1].
    - Coerce invalid phone numbers to start with 09, or use placeholder +63 900XXXXXXX if missing[cite: 1].
    """
    print("Executing Alorica Job...")
    # TODO: Implement gspread authentication and data parsing logic here.
    # TODO: Implement requests.post() to ALORICA_FORM_URL.

def main():
    # Both jobs are scheduled every hour between 8 AM and 1 AM PHT[cite: 1].
    # IBEX runs at :09 and Alorica at :39[cite: 1].
    schedule.every().hour.at(":09").do(run_ibex_job)
    schedule.every().hour.at(":39").do(run_alorica_job)

    print("Cursor Cloud Agent Initialized. Waiting for scheduled tasks...")

    while True:
        manila_tz = pytz.timezone('Asia/Manila')
        current_hour = datetime.now(manila_tz).hour
        
        # Operational window: 8 AM to 1 AM PHT[cite: 1].
        if 8 <= current_hour <= 23 or current_hour == 0:
            schedule.run_pending()
        
        time.sleep(30)

if __name__ == "__main__":
    main()
