#!/usr/bin/env python3
"""Upload one Alorica referral. Does not submit outside 08:00-01:00 Asia/Manila."""

import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SHEET_URL = "https://docs.google.com/spreadsheets/d/1NoRX955F0dpxMReiC-6lcd3hgxFDccS3H9hzabTQghE/edit"
FORM_URL = "https://forms.talkpush.com/form/25909c5f-7af0-44e4-8a58-64ecfbb9dc5f"
REFERRER_NAME = "Edward Belacse"
TZ = ZoneInfo("Asia/Manila")
ABROAD = {"dubai", "uae", "singapore", "usa", "zimbabwe", "malaysia"}
TABS = [
    {"name": "MODERN TRACTION", "col": 21, "start": 2, "first": 2, "last": 3, "phone": 4, "email": 5, "loc": 6, "exp": 8},
    {"name": "NEW AFFILIATE REFERRAL SYSTEM", "col": 15, "start": 2, "first": 1, "last": 0, "phone": 2, "email": 4, "loc": 3, "exp": 5},
    {"name": "JOBSTREET", "col": 24, "start": 2, "first": 2, "last": 3, "phone": 4, "email": 5, "loc": 6, "exp": 8},
]
MAX_ATTEMPTS = 5
STAMP = "/tmp/alorica-hourly-stamp"


def in_window(now):
    # 08:00 through 01:59. The 01:00 run is included; 02:00-07:59 is not.
    return now.hour >= 8 or now.hour <= 1


def mobile_e164(phone_str):
    raw = str(phone_str or "")
    # "9666712181/9561725391" or "9666712181 / 9561725391" — use the first number.
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("63") and len(digits) >= 12:
        digits = digits[-10:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits.startswith("9"):
        return "+63" + digits
    return None


def site_for(location):
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


def exp_for(exp_str):
    exp = str(exp_str).lower().strip()
    if any(x in exp for x in ["2 year", "3 year", "4 year", "5 year"]):
        return "24+ mos BPO"
    if "1 year" in exp:
        return "12–23 mos BPO"
    if "6" in exp and "11" in exp:
        return "6–11 mos BPO"
    return "0–5 mos BPO"


def first_email(email_str):
    email = str(email_str or "").strip().lower()
    # "davd33177@gmail.com / ujosh809@gmail.com" — use the first address.
    if "/" in email:
        email = email.split("/", 1)[0].strip()
    if email.endswith(".con"):
        email = email[:-4] + ".com"
    return email


def ready(row, tab):
    if len(row) < tab["col"]:
        row = row + [""] * (tab["col"] - len(row))
    if row[tab["col"] - 1].strip():
        return None
    first = row[tab["first"]].strip() if len(row) > tab["first"] else ""
    last = row[tab["last"]].strip() if len(row) > tab["last"] else ""
    email = first_email(row[tab["email"]] if len(row) > tab["email"] else "")
    phone_raw = row[tab["phone"]].strip() if len(row) > tab["phone"] else ""
    loc = row[tab["loc"]].strip() if len(row) > tab["loc"] else ""
    exp_raw = row[tab["exp"]].strip() if len(row) > tab["exp"] else ""
    if not email or "@" not in email or email.endswith("g,ail.com") or not first or loc in ["N/A", ""]:
        return None
    if "abroad" in loc.lower() or loc.lower() in ABROAD:
        return None
    if re.fullmatch(r"[A-Za-z]?\d{3,}", loc):
        return None
    e164 = mobile_e164(phone_raw)
    if not e164:
        return None
    return {
        "first": first,
        "last": last,
        "email": email,
        "phone_raw": phone_raw,
        "e164": e164,
        "city": loc,
        "site": site_for(loc),
        "exp_raw": exp_raw,
        "exp": exp_for(exp_raw),
    }


def worksheet_client():
    info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds).open_by_url(SHEET_URL)


def fill_form(page, candidate):
    page.goto(FORM_URL, wait_until="domcontentloaded", timeout=30000)
    page.get_by_placeholder("John Doe").wait_for()
    page.get_by_placeholder("John Doe").fill(REFERRER_NAME)
    page.get_by_placeholder("e.g. John").fill(candidate["first"])
    page.get_by_placeholder("e.g. Doe").fill(candidate["last"])
    page.get_by_placeholder("you@email.com").fill(candidate["email"])
    page.locator("select.PhoneInputCountrySelect").select_option("PH")
    tel = page.locator("input[type=tel]")
    tel.click()
    tel.fill(candidate["e164"])
    page.get_by_role("combobox").nth(1).click()
    page.get_by_role("option", name=candidate["site"], exact=True).click()
    page.get_by_role("combobox").nth(2).click()
    page.get_by_role("option", name=candidate["exp"], exact=True).click()
    page.get_by_role("radio", name="Community Referrer from Barangay").click()
    page.locator("input[type=text]").last.fill(candidate["city"])
    page.wait_for_timeout(300)
    return page.evaluate(
        """() => ({
          name: document.querySelector('input[placeholder="John Doe"]').value,
          phone: document.querySelector('input[type=tel]').value,
          first: document.querySelector('input[placeholder="e.g. John"]').value,
          last: document.querySelector('input[placeholder="e.g. Doe"]').value,
          email: document.querySelector('input[type=email]').value,
          city: document.querySelectorAll('input[type=text]')[document.querySelectorAll('input[type=text]').length - 1].value,
          combos: Array.from(document.querySelectorAll('[role=combobox]')).map(c => c.innerText.replace(/\\s+/g,' ').trim()),
          radio: Array.from(document.querySelectorAll('[role=radio]')).filter(r => r.getAttribute('aria-checked')==='true').map(r => r.getAttribute('value'))
        })"""
    )


def phone_ok(shown, e164):
    return re.sub(r"\D", "", shown) == re.sub(r"\D", "", e164) and shown.startswith("+63")


def main():
    now = datetime.now(TZ)
    hour_key = now.strftime("%Y-%m-%d-%H")
    print(f"NOW {now.strftime('%Y-%m-%d %H:%M %Z')}")
    if "--force" not in sys.argv and not in_window(now):
        print("OUTSIDE_WINDOW 08:00-01:00 Asia/Manila. No upload.")
        return 0
    if "--force" not in sys.argv and os.path.exists(STAMP) and open(STAMP).read().strip() == hour_key:
        print(f"ALREADY_UPLOADED_THIS_HOUR {hour_key}")
        return 0

    doc = worksheet_client()
    attempts = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 2200})
        for tab in TABS:
            ws = doc.worksheet(tab["name"])
            data = ws.get_all_values()
            if not data or "ALORICA" not in str(data[0][tab["col"] - 1] if len(data[0]) >= tab["col"] else "").upper():
                print(f"SKIP_TAB {tab['name']} header mismatch")
                continue
            for row_idx in range(tab["start"] - 1, len(data)):
                if attempts >= MAX_ATTEMPTS:
                    print("ATTEMPT_CAP")
                    browser.close()
                    return 1
                candidate = ready(data[row_idx], tab)
                if not candidate:
                    continue
                row_num = row_idx + 1
                remark = ws.cell(row_num, tab["col"]).value or ""
                if remark.strip():
                    continue
                attempts += 1
                posts = []

                def on_response(resp, posts=posts):
                    if resp.request.method == "POST" and "/api/submit-lead" in resp.url:
                        try:
                            body = resp.json()
                        except Exception:
                            body = {}
                        posts.append(
                            {
                                "status": resp.status,
                                "success": body.get("success"),
                                "code": body.get("code"),
                            }
                        )

                page.on("response", on_response)
                shown = fill_form(page, candidate)
                print(f"TAB {tab['name']} ROW {row_num}")
                print("Q What is your Name")
                print(f"A {shown['name']}")
                print("Q What is your Referral's First Name")
                print(f"A {shown['first']}")
                print("Q What is your Referral's Last Name")
                print(f"A {shown['last']}")
                print("Q What is your Referral's Email")
                print(f"A {shown['email']}")
                print("Q What is your referral's phone number?")
                print(f"A {shown['phone']}")
                print("Q What is your refereral's preferred site?")
                print(f"A {shown['combos'][0] if shown['combos'] else ''}")
                print("Q What is your Referral's Experience")
                print(f"A {shown['combos'][1] if len(shown['combos']) > 1 else ''}")
                print("Q Which of the following communities are you a part of?")
                print(f"A {shown['radio'][0] if shown['radio'] else ''}")
                print("Q Provide the name of the City")
                print(f"A {shown['city']}")
                if (
                    shown["name"] != REFERRER_NAME
                    or not phone_ok(shown["phone"], candidate["e164"])
                    or shown["email"].strip().lower() != candidate["email"]
                ):
                    page.remove_listener("response", on_response)
                    print("ABORT name, phone, or email mismatch. Not submitted.")
                    browser.close()
                    return 1
                page.screenshot(path=f"/opt/cursor/artifacts/routine-{row_num}-before.png", full_page=True)
                page.get_by_test_id("button-submit").click()
                page.wait_for_timeout(4000)
                text = page.inner_text("body").lower()
                page.screenshot(path=f"/opt/cursor/artifacts/routine-{row_num}-result.png", full_page=True)
                duplicate = "already applied" in text or any(x.get("code") == "duplicate_application" for x in posts)
                submitted = (not duplicate) and (
                    "submitted successfully" in text or any(x.get("success") is True for x in posts)
                )
                page.remove_listener("response", on_response)
                if duplicate:
                    ws.update_cell(row_num, tab["col"], "Duplicate")
                    print(f"RESULT duplicate MARKED Duplicate")
                    continue
                if submitted:
                    ws.update_cell(row_num, tab["col"], "Executive Team")
                    with open(STAMP, "w") as stamp:
                        stamp.write(hour_key)
                    print("RESULT submitted MARKED Executive Team")
                    browser.close()
                    return 0
                print("RESULT unknown. Sheet not changed.")
                browser.close()
                return 1
        browser.close()
    print("NO_CANDIDATE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
