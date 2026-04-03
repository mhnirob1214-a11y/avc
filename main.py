import os
import asyncio
import re
import requests
import time
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ===== কনফিগারেশন =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://185.2.83.39/ints/agent/SMSCDRReports"
LOGIN_URL = "http://185.2.83.39/ints/login"
FB_URL = "https://otp-manager-511ec-default-rtdb.asia-southeast1.firebasedatabase.app/bot"

ADMIN_LINK = "https://t.me/Xero_Ridoy" # আপনার এডমিন লিংক
BOT_LINK = "https://t.me/FTC_SUPER_SMS_BOT" # আপনার বট লিংক

# ক্যাশ মেমোরি: {"number|sms_text": "last_seen_time"}
sent_msgs = {}
START_TIME = time.time()

def extract_otp(msg):
    match = re.search(r'\b(\d{4,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
    return match.group(1) if match else "N/A"

def parse_dt(d_str):
    try:
        parts = d_str.split(' ')
        return parts[0][-5:], parts[1] # Returns '04-03', '11:32:11'
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

def send_telegram(date_str, num, msg, otp):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    masked = num[:4] + "XXX" + num[-4:] if len(num) > 8 else num

    # আপনার চাওয়া নির্দিষ্ট ফরম্যাট (কোটেশন বা <code> ট্যাগ ব্যবহার করে)
    text = f"🆕 <b>NEW SMS RECEIVED</b>\n\n" \
           f"🕒 Time: {date_str}\n" \
           f"📱 Number: <code>{masked}</code>\n"
    
    if otp != "N/A":
        text += f"🔑 OTP Code: <code>{otp}</code>\n\n"
    else:
        text += "\n"
        
    text += f"💬 Message:\n<code>{msg}</code>"

    # বাটন সেটআপ
    keyboard = []
    if otp != "N/A":
        keyboard.append([{"text": f"📋 {otp}", "callback_data": "ignore_copy"}])
    
    keyboard.append([
        {"text": "🤖 বট লিংক", "url": BOT_LINK},
        {"text": "👨‍💻 এডমিন", "url": ADMIN_LINK}
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
                    try {{
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
                        return false;
                    }} catch (e) {{ return false; }}
                }}""")
                return True
            except: return False

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
                    found_new = False

                    if is_first_scan:
                        # প্রথম স্ক্যানে শুধু লেটেস্ট মেসেজটি পাঠাবে
                        d_short, t_short = parse_dt(latest['date'])
                        otp = extract_otp(latest['sms'])
                        
                        tg_ok = send_telegram(latest['date'], latest['num'], latest['sms'], otp)
                        fb_ok = update_firebase(latest['num'], latest['sms'], latest['date'])
                        
                        sent_msgs[f"{latest['num']}|{latest['sms']}"] = latest['date']
                        
                        grp_stat = "✅" if tg_ok else "❌"
                        db_stat = "✅" if fb_ok else "❌"
                        print(f"🆕{d_short}◻️{t_short}◻️: {latest['num']}\n💬{latest['sms']}\nGrupe {grp_stat} DB {db_stat}\n")
                        
                        # বাকিগুলো সাইলেন্টলি ক্যাশে রাখবে
                        for item in valid_rows[1:]:
                            sent_msgs[f"{item['num']}|{item['sms']}"] = item['date']
                        
                        is_first_scan = False
                    
                    else:
                        # রিভার্স লুপ যাতে সিরিয়াল ঠিক থাকে (নিচ থেকে উপরে)
                        for item in reversed(valid_rows):
                            uid = f"{item['num']}|{item['sms']}"
                            
                            # ১. সম্পূর্ণ নতুন মেসেজ (গ্রুপ + ডাটাবেজ)
                            if uid not in sent_msgs:
                                found_new = True
                                d_short, t_short = parse_dt(item['date'])
                                otp = extract_otp(item['sms'])
                                
                                tg_ok = send_telegram(item['date'], item['num'], item['sms'], otp)
                                fb_ok = update_firebase(item['num'], item['sms'], item['date'])
                                sent_msgs[uid] = item['date']
                                
                                grp_stat = "✅" if tg_ok else "❌"
                                db_stat = "✅" if fb_ok else "❌"
                                print(f"🆕{d_short}◻️{t_short}◻️: {item['num']}\n💬{item['sms']}\nGrupe {grp_stat} DB {db_stat}\n")
                            
                            # ২. মেসেজ একই কিন্তু সময় আলাদা (শুধুমাত্র ডাটাবেজ আপডেট)
                            elif sent_msgs[uid] != item['date']:
                                new_db_text = f"{item['sms']} (Updated: {item['date']})"
                                update_firebase(item['num'], new_db_text, item['date'])
                                sent_msgs[uid] = item['date']
                        
                        # ৩. নতুন কিছু না পেলে আপনার দেওয়া সংক্ষিপ্ত লগ প্রিন্ট করবে
                        if not found_new:
                            d_short, t_short = parse_dt(latest['date'])
                            otp = extract_otp(latest['sms'])
                            print(f"🫆{d_short}◻️{t_short}◻️: {latest['num']}💬 {otp} Grupe ✅ DB ✅ ")

                # মেমোরি ক্লিন আপ (ক্যাশ বেশি বড় হলে প্রথম আইটেম ডিলিট করবে)
                if len(sent_msgs) > 2000:
                    del sent_msgs[next(iter(sent_msgs))]

            except Exception as e:
                pass
            
            await asyncio.sleep(4)

if __name__ == "__main__":
    asyncio.run(start_bot())
