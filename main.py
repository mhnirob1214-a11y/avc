# -*- coding: utf-8 -*-
import os
import asyncio
import re
import requests
import time
import argparse
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ===== CLI থেকে Service ইনপুট =====
parser = argparse.ArgumentParser(description="FTC SMS Bot")
parser.add_argument("--service", type=str, default="FTC SMS", help="Service name to show in Telegram messages")
args = parser.parse_args()
SERVICE_SOURCE = args.service  # CLI থেকে নেওয়া service

# ===== কনফিগারেশন =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://185.2.83.39/ints/agent/SMSCDRReports"
LOGIN_URL = "http://185.2.83.39/ints/login"
FB_URL = "https://otp-manager-511ec-default-rtdb.asia-southeast1.firebasedatabase.app/bot"

ADMIN_LINK = "https://t.me/Xero_Ridoy"
BOT_LINK = "https://t.me/FTC_SUPER_SMS_BOT"

sent_msgs = {}
START_TIME = time.time()

# ===== ইউটিলিটি ফাংশন =====
def extract_otp(msg):
    match = re.search(r'\b(\d{4,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
    return match.group(1) if match else "N/A"

def parse_dt(d_str):
    try:
        parts = d_str.split(' ')
        return parts[0][-5:], parts[1]  # '04-03', '11:32:11'
    except:
        return "??-??", "??:??:??"

def update_firebase(num, msg, date_str):
    try:
        clean_num = re.sub(r'\D', '', num)
        url = f"{FB_URL}/sms_logs/{clean_num}.json"
        payload = {"number": num, "message": msg, "time": date_str, "paid": False}
        res = requests.put(url, json=payload, timeout=8)
        return res.status_code == 200
    except:
        return False

# ===== Telegram ম্যাসেজ পাঠানোর ফাংশন =====
def send_telegram(date_str, num, msg, otp, source, is_update=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    masked = num[:4] + "XXX" + num[-4:] if len(num) > 8 else num

    header = "🔄 <b><u>ᴜᴘᴅᴀᴛᴇᴅ sᴍs ʀᴇᴄᴇɪᴠᴇᴅ</u></b>" if is_update else "🆕 <b><u>ɴᴇᴡ sᴍs ʀᴇᴄᴇɪᴠᴇᴅ</u></b>"
    divider = "<b>━━━━━━━━━━━━━━━━━━</b>"

    text = f"{header}\n{divider}\n\n" \
           f"🕒 <b>Time:</b> <code>{date_str}</code>\n" \
           f"📱 <b>Number:</b> <code>{masked}</code>\n" \
           f"🛠️ <b>Service:</b> <code>{source}</code>\n\n"

    if otp != "N/A":
        text += f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n"

    text += f"{divider}\n💬 <b>Message:</b>\n└ <blockquote>{msg}</blockquote>\n{divider}"

    keyboard = []
    if otp != "N/A":
        keyboard.append([{
            "text": f"📋 Copy OTP: {otp}",
            "switch_inline_query_current_chat": otp
        }])

    keyboard.append([
        {"text": "🤖 FTC BOT", "url": BOT_LINK},
        {"text": "👨‍💻 Admin", "url": ADMIN_LINK}
    ])

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": keyboard}
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except:
        return False

# ===== Bot স্ক্যান লজিক =====
async def start_bot():
    print("🚀 বট চালু হচ্ছে...")

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        async def login():
            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                await page.evaluate(f"""() => {{
                    const myUser = "{MY_USER}"; const myPass = "{MY_PASS}";
                    let userField, passField, ansField;
                    document.querySelectorAll('input').forEach(inp => {{
                        let p = (inp.placeholder || "").toLowerCase();
                        if (inp.type === 'password') passField = inp;
                        else if (p.includes('user') || inp.type === 'text') {{ if (!userField && !p.includes('answer')) userField = inp; }}
                        if (p.includes('answer') || (inp.name || "").includes('ans')) ansField = inp;
                    }});
                    let match = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                    let sum = match ? (parseInt(match[1]) + parseInt(match[2])) : "";
                    if (userField && passField && ansField && sum !== "") {{
                        userField.value = myUser; passField.value = myPass; ansField.value = sum;
                        userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        ansField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        for(let b of document.querySelectorAll('button, input[type="submit"]')) {{
                            if((b.innerText || b.value || "").toLowerCase().includes('login')) {{ b.click(); return true; }}
                        }}
                    }}
                }}""")
                return True
            except:
                return False

        await login()
        is_first_scan = True

        while True:
            try:
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)

                if "login" in page.url:
                    await login()
                    continue

                valid_rows = []
                rows = await page.query_selector_all("table tbody tr")
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 6:
                        d = (await cols[0].inner_text()).strip()
                        n = (await cols[2].inner_text()).strip()
                        s = (await cols[5].inner_text()).strip()
                        if d and len(re.sub(r'\D','',n)) >= 8:
                            valid_rows.append({"date": d, "num": n, "sms": s})

                if valid_rows:
                    latest = valid_rows[0]
                    found_update = False

                    if is_first_scan:
                        d_short, t_short = parse_dt(latest['date'])
                        otp = extract_otp(latest['sms'])
                        tg = send_telegram(latest['date'], latest['num'], latest['sms'], otp, SERVICE_SOURCE)
                        fb = update_firebase(latest['num'], latest['sms'], latest['date'])
                        sent_msgs[f"{latest['num']}|{latest['sms']}"] = latest['date']
                        print(f"🆕{d_short}◻️{t_short}◻️: {latest['num']}💬{latest['sms']}\nGrupe {'✅' if tg else '❌'} DB {'✅' if fb else '❌'}\n")
                        for item in valid_rows[1:]:
                            sent_msgs[f"{item['num']}|{item['sms']}"] = item['date']
                        is_first_scan = False

                    else:
                        for item in reversed(valid_rows):
                            uid = f"{item['num']}|{item['sms']}"
                            d_short, t_short = parse_dt(item['date'])
                            otp = extract_otp(item['sms'])

                            if uid not in sent_msgs:
                                tg = send_telegram(item['date'], item['num'], item['sms'], otp, SERVICE_SOURCE, is_update=False)
                                fb = update_firebase(item['num'], item['sms'], item['date'])
                                sent_msgs[uid] = item['date']
                                print(f"🆕{d_short}◻️{t_short}◻️: {item['num']}💬{item['sms']}\nGrupe {'✅' if tg else '❌'} DB {'✅' if fb else '❌'}\n")
                                found_update = True

                            elif sent_msgs[uid] != item['date']:
                                tg = send_telegram(item['date'], item['num'], f"{item['sms']} (Update)", otp, SERVICE_SOURCE, is_update=True)
                                fb = update_firebase(item['num'], f"{item['sms']} (Update)", item['date'])
                                sent_msgs[uid] = item['date']
                                print(f"🔄{d_short}◻️{t_short}◻️: {item['num']}💬{item['sms']}\nGrupe {'✅' if tg else '❌'} DB {'✅' if fb else '❌'}\n")
                                found_update = True

                        if not found_update:
                            d_short, t_short = parse_dt(latest['date'])
                            otp = extract_otp(latest['sms'])
                            print(f"🫆{d_short}◻️{t_short}◻️: {latest['num']}💬 {otp} Grupe ✅ DB ✅ ")

                if len(sent_msgs) > 2000:
                    sent_msgs.clear()

            except Exception:
                pass

            await asyncio.sleep(4)

if __name__ == "__main__":
    asyncio.run(start_bot())
