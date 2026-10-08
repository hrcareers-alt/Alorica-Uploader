import argparse
import json
import os
import re
import sys

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

load_dotenv()

ALORICA_LINK = "https://forms.talkpush.com/form/25909c5f-7af0-44e4-8a58-64ecfbb9dc5f"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1NoRX955F0dpxMReiC-6lcd3hgxFDccS3H9hzabTQghE/edit"
REFERRER_NAME = "Executive Team"
SUCCESS_REMARK = "Executive Team"

TABS = [
    {
        "name": "MODERN TRACTION",
        "col": 21,
        "start": 2,
        "first": 2,
        "last": 3,
        "phone": 4,
        "email": 5,
        "loc": 6,
        "exp": 8,
    },
    {
        "name": "NEW AFFILIATE REFERRAL SYSTEM",
        "col": 15,
        "start": 2,
        "first": 1,
        "last": 0,
        "phone": 2,
        "email": 4,
        "loc": 3,
        "exp": 5,
    },
    {
        "name": "JOBSTREET",
        "col": 24,
        "start": 2,
        "first": 2,
        "last": 3,
        "phone": 4,
        "email": 5,
        "loc": 6,
        "exp": 8,
    },
]


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
        return None
    digits = re.sub(r"\D", "", str(phone_str))
    if len(digits) >= 10:
        return "+63 9" + digits[-9:]
    return None


def get_alorica_site(location):
    loc = str(location).lower().strip()
    if not loc or loc in ["n/a", "remote", "wfh"]:
        return "Cebu"
    if loc in ["philippines", "ph", "phils"]:
        return "Makati MJ Plaza"
    if any(x in loc for x in ["tagbilaran", "bohol", "cebu"]):
        return "Cebu"
    if "bulacan" in loc or "hagonoy" in loc:
        return "Centris"
    if "tayabas" in loc or "quezon" in loc or "tiaong" in loc:
        return "Lipa"
    if "bataan" in loc:
        return "Clark"
    if "morong" in loc or "rizal" in loc:
        return "Marikina"
    if "calasiao" in loc:
        return "Ilocos"
    return "Cebu"


def get_alorica_exp(exp_str):
    exp = str(exp_str).lower().strip()
    if "fresh" in exp:
        return "Fresh Graduate"
    if "non bpo" in exp or "non-bpo" in exp:
        return "Non BPO Work Exp"
    if any(x in exp for x in ["3 year", "3+ year", "above", "24+", "2 year", "2+ year"]):
        return "24+ mos BPO"
    if "1 year" in exp or "12-23" in exp or "12–23" in exp:
        return "12–23 mos BPO"
    if "6-11" in exp or "6–11" in exp or "6 to 11" in exp:
        return "6–11 mos BPO"
    return "0–5 mos BPO"


def is_incomplete(email, first_name, loc, phone):
    return (
        not email
        or "@" not in email
        or email.endswith("g,ail.com")
        or not first_name
        or loc in ["N/A", ""]
        or not phone
    )


def is_abroad(loc):
    loc_lower = loc.lower()
    return "abroad" in loc_lower or loc_lower in [
        "dubai",
        "uae",
        "singapore",
        "usa",
        "zimbabwe",
        "malaysia",
    ]


def submit_alorica_form(page, first_name, last_name, email, phone, site, exp):
    page.goto(ALORICA_LINK, wait_until="domcontentloaded", timeout=30000)
    page.get_by_placeholder("John Doe").wait_for(timeout=15000)

    page.get_by_placeholder("John Doe").fill(REFERRER_NAME)
    page.get_by_placeholder("e.g. John").fill(first_name)
    page.get_by_placeholder("e.g. Doe").fill(last_name)
    page.get_by_placeholder("you@email.com").fill(email)

    page.locator('select[aria-label="Phone number country"]').select_option(label="Philippines")
    phone_input = page.locator("input.PhoneInputInput")
    phone_input.fill("")
    phone_input.fill(phone)

    # Country select is first; preferred site and experience follow.
    page.locator("select").nth(1).select_option(label=site)
    page.locator("select").nth(2).select_option(label=exp)

    page.get_by_text("Community Referrer from Barangay", exact=True).click()

    with page.expect_navigation(timeout=30000):
        page.get_by_role("button", name="Submit").click()

    body = page.locator("body").inner_text(timeout=15000)
    lower = body.lower()
    if any(token in lower for token in ["thank", "success", "submitted", "received"]):
        return True, body[:500]
    # Some Talkpush flows land on a confirmation without those words; accept non-form URL.
    if "form/" not in page.url.lower() or "proceed" not in lower:
        return True, f"url={page.url} body={body[:300]}"
    return False, f"No confirmation detected. url={page.url} body={body[:500]}"


def run_alorica_pipeline(limit=None):
    gc = setup_gspread()
    doc = gc.open_by_url(SHEET_URL)
    processed = 0
    uploaded = 0
    skipped = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        for tab_info in TABS:
            if limit is not None and processed >= limit:
                break

            try:
                ws = doc.worksheet(tab_info["name"])
                data = ws.get_all_values()
            except Exception as e:
                print(f"Could not load tab {tab_info['name']}: {e}")
                continue

            if len(data) > 0 and "ALORICA" not in str(data[0][tab_info["col"] - 1]).upper():
                print(f"Skipping {tab_info['name']}: Alorica header not found")
                continue

            for row_idx in range(tab_info["start"] - 1, len(data)):
                if limit is not None and processed >= limit:
                    break

                row = data[row_idx]
                if len(row) < tab_info["col"]:
                    row.extend([""] * (tab_info["col"] - len(row)))

                current_remark = ws.cell(row_idx + 1, tab_info["col"]).value or ""
                if current_remark.strip():
                    continue

                first_name = row[tab_info["first"]].strip() if len(row) > tab_info["first"] else ""
                last_name = row[tab_info["last"]].strip() if len(row) > tab_info["last"] else ""
                email = row[tab_info["email"]].strip().lower() if len(row) > tab_info["email"] else ""
                phone = format_alorica_phone(row[tab_info["phone"]] if len(row) > tab_info["phone"] else "")
                loc = row[tab_info["loc"]].strip() if len(row) > tab_info["loc"] else ""
                exp = get_alorica_exp(row[tab_info["exp"]] if len(row) > tab_info["exp"] else "")

                if email.endswith(".con"):
                    email = email.replace(".con", ".com")

                if is_incomplete(email, first_name, loc, phone):
                    ws.update_cell(row_idx + 1, tab_info["col"], "Incomplete Info")
                    skipped += 1
                    print(f"Incomplete Info: {tab_info['name']} row {row_idx + 1}")
                    continue

                if is_abroad(loc):
                    ws.update_cell(row_idx + 1, tab_info["col"], "INVALID")
                    skipped += 1
                    print(f"INVALID abroad: {tab_info['name']} row {row_idx + 1}")
                    continue

                site = get_alorica_site(loc)
                page = context.new_page()
                try:
                    ok, detail = submit_alorica_form(
                        page, first_name, last_name, email, phone, site, exp
                    )
                    if ok:
                        ws.update_cell(row_idx + 1, tab_info["col"], SUCCESS_REMARK)
                        uploaded += 1
                        processed += 1
                        print(
                            f"Uploaded: {tab_info['name']} row {row_idx + 1} "
                            f"site={site} exp={exp}"
                        )
                    else:
                        failed += 1
                        print(
                            f"Submit unclear for {tab_info['name']} row {row_idx + 1}: {detail}"
                        )
                except Exception as e:
                    failed += 1
                    print(
                        f"Failed Alorica submission for Row {row_idx + 1} "
                        f"({tab_info['name']}): {e}"
                    )
                finally:
                    page.close()

        browser.close()

    print(
        f"Done. uploaded={uploaded} skipped={skipped} failed={failed} "
        f"processed_limit={processed} limit={limit}"
    )
    return uploaded, skipped, failed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Upload Alorica referrals from Google Sheets")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of successful uploads this run (useful for smoke tests)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    uploaded, skipped, failed = run_alorica_pipeline(limit=args.limit)
    if uploaded == 0 and failed > 0:
        sys.exit(1)
