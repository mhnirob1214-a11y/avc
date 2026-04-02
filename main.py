import os
import asyncio
import re
import requests
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ===== কনফিগারেশন =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://185.2.83.39/ints/agent/SMSCDRReports"
LOGIN_URL = "http://185.2.83.39/login"

sent_cache = set()
START_TIME = time.time()

def get_now():
    return datetime.now().strftime('%H:%M:%S')

async def start_bot():
    print(f"[{get_now()}] 🚀 FTC PRO V23 চালু হচ্ছে...")
    async with async_playwright() as p:
        # আসল ব্রাউজারের মতো ইউজার এজেন্ট ব্যবহার করা হচ্ছে
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        async def login():
            print(f"[{get_now()}] 🔑 লগিন করার চেষ্টা করছি...")
            try:
                # পেজ লোড হওয়া এবং নেটওয়ার্ক শান্ত হওয়া পর্যন্ত অপেক্ষা
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                
                # পেজ কি খালি? তা চেক করা
                inputs_count = await page.locator('input').count()
                print(f"[{get_now()}] 📄 পেজ লোড হয়েছে। মোট ইনপুট ফিল্ড পাওয়া গেছে: {inputs_count}টি")

                if inputs_count == 0:
                    print(f"[{get_now()}] ⚠️ কোনো ইনপুট ফিল্ড পাওয়া যায়নি! আবার চেষ্টা করছি...")
                    await page.reload(wait_until="networkidle")

                # ইউজারনেম এবং পাসওয়ার্ড ফিল্ড স্মার্টলি খোঁজা
                user_field = page.locator('input[type="text"], input[name*="user" i], input[placeholder*="user" i]').first
                pass_field = page.locator('input[type="password"]').first
                
                await user_field.wait_for(state="visible", timeout=15000)
                await user_field.fill(MY_USER)
                await pass_field.fill(MY_PASS)

                # ক্যাপচা সমাধান
                content = await page.content()
                match = re.search(r'What is\s+(\d+)\s*\+\s*(\d+)', content, re.IGNORECASE)
                if match:
                    ans_val = str(int(match[1]) + int(match[2]))
                    await page.locator('input[name="ans"], input[placeholder*="ans" i]').first.fill(ans_val)
                    print(f"[{get_now()}] ✅ ক্যাপচা সলভড: {ans_val}")

                # লগিন বাটন ক্লিক
                await page.locator('button[type="submit"], input[type="submit"], button:has-text("Login")').first.click()
                await page.wait_for_timeout(5000)
                
                if "login" not in page.url:
                    print(f"[{get_now()}] 🎉 লগিন সফল!")
                else:
                    print(f"[{get_now()}] ⚠️ লগিন ব্যর্থ হতে পারে, ইউআরএল চেক করুন।")

            except Exception as e:
                print(f"[{get_now()}] ❌ লগিন এরর: {str(e)}")

        await login()

        while True:
            if time.time() - START_TIME > 18000:
                print(f"[{get_now()}] 🔄 সেশন রিস্টার্ট হচ্ছে...")
                break

            try:
                if "login" in page.url: 
                    await login()
                
                await page.goto(TARGET_URL, wait_until="load", timeout=60000)
                await page.wait_for_selector("table tbody tr", timeout=20000)
                
                rows = await page.query_selector_all("table tbody tr")
                found_new = False
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 6:
                        num = (await cols[2].inner_text()).strip()
                        sms = (await cols[5].inner_text()).strip()
                        uid = f"{num}|{sms}"
                        
                        if uid not in sent_cache:
                            # টেলিগ্রাম মেসেজ লজিক
                            masked = num[:4] + "XXX" + num[-4:] if len(num) > 8 else num
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                                json={"chat_id": CHAT_ID, "text": f"🆕 <b>SMS</b>\n📱 {masked}\n💬 {sms}", "parse_mode": "HTML"})
                            sent_cache.add(uid)
                            found_new = True
                            if len(sent_cache) > 500: sent_cache.pop()
                
                print(f"[{get_now()}] ⏳ স্ক্যানিং... {'নতুন ডাটা পাওয়া গেছে' if found_new else 'নতুন ডাটা নেই'}")
            except Exception as e:
                print(f"[{get_now()}] ⚠️ লুপ এরর: {str(e)}")
                await page.wait_for_timeout(5000)
            
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(start_bot())
