import os
import re
import asyncio
import logging
import threading
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# ----------------------------------------------------
# CẤU HÌNH HỆ THỐNG
# ----------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8997592489:AAE8Ar60r1TBggUaexdzyC6c9E3veywivcI")
CHAT_ID = os.getenv("CHAT_ID", "-1004379710582")
PORT = int(os.getenv("PORT", 8080))

SCHEDULE_MAP = {
    0: {"code": "py", "name": "Phú Yên"},
    1: {"code": "dlk", "name": "Đắk Lắk"},
    2: {"code": "kh", "name": "Khánh Hòa"},
    3: {"code": "qt", "name": "Quảng Trị"},
    4: {"code": "gl", "name": "Gia Lai"},
    5: {"code": "qng", "name": "Quảng Ngãi"},
    6: {"code": "kt", "name": "Kon Tum"}
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cache biến toàn cục
CACHE_DATA = None
CACHE_TIME = None

# ----------------------------------------------------
# FLASK WEB SERVER
# ----------------------------------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot status: Active", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ----------------------------------------------------
# CÀO DỮ LIỆU KQXS
# ----------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
}

def fetch_from_source_1(date_str, province_code):
    try:
        url = f"https://www.minhngoc.net.vn/ket-qua-xo-so/mien-trung/{date_str}.html"
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            box = soup.find("div", class_=re.compile(f".*{province_code}.*", re.I)) or soup
            numbers = set()
            for td in box.find_all(["td", "div"], class_=re.compile(r"giai|so", re.I)):
                txt = td.text.strip()
                found = re.findall(r"\b\d{2,6}\b", txt)
                for num in found:
                    numbers.add(num[-2:])
            if len(numbers) >= 10:
                return list(numbers)
    except Exception as e:
        logger.warning(f"Source 1 error ({date_str}): {e}")
    return None

def fetch_from_source_2(date_str):
    try:
        url = f"https://xoso.me/kqxs-mien-trung-ngay-{date_str}.html"
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            numbers = set()
            for td in soup.find_all("span", class_=re.compile(r"v-giai|duoc-ve", re.I)):
                txt = td.text.strip()
                if len(txt) >= 2 and txt.isdigit():
                    numbers.add(txt[-2:])
            if len(numbers) >= 10:
                return list(numbers)
    except Exception as e:
        logger.warning(f"Source 2 error ({date_str}): {e}")
    return None

def get_kqxs_by_date(dt):
    date_str = dt.strftime("%d-%m-%Y")
    province_info = SCHEDULE_MAP[dt.weekday()]
    
    data = fetch_from_source_1(date_str, province_info["code"])
    if not data:
        data = fetch_from_source_2(date_str)
        
    return data or [], province_info["name"]

async def calculate_lo_gan_async():
    global CACHE_DATA, CACHE_TIME
    
    # Kiểm tra Cache nếu còn hiệu lực dưới 1 giờ
    if CACHE_DATA and CACHE_TIME and (datetime.now() - CACHE_TIME).total_seconds() < 3600:
        return CACHE_DATA

    today = datetime.now().date()
    history = []

    for i in range(1, 61):
        target_date = today - timedelta(days=i)
        # Chạy request cào dữ liệu trên threadpool để không block event loop
        numbers, province_name = await asyncio.to_thread(get_kqxs_by_date, target_date)
        history.append({
            "date": target_date,
            "province": province_name,
            "numbers": numbers
        })
        await asyncio.sleep(0.05)

    gan_dict = {}
    for num in range(100):
        num_str = f"{num:02d}"
        days_gan = 0
        last_date = None
        last_province = "Chưa về"
        
        for day_data in history:
            if num_str in day_data["numbers"]:
                last_date = day_data["date"].strftime("%d/%m/%Y")
                last_province = day_data["province"]
                break
            else:
                days_gan += 1

        gan_dict[num_str] = {
            "days_gan": days_gan,
            "last_date": last_date if last_date else "Trên 60 ngày",
            "last_province": last_province
        }

    sorted_gan = sorted(gan_dict.items(), key=lambda x: x[1]["days_gan"], reverse=True)[:10]
    
    # Cập nhật cache
    CACHE_DATA = sorted_gan
    CACHE_TIME = datetime.now()
    return sorted_gan

def format_report(sorted_gan):
    msg = "<b>THỐNG KÊ LÔ GAN GỘP ĐA ĐÀI - XSMT (60 NGÀY)</b>\n"
    msg += "<i>(Quét theo lịch 7 đài cố định)</i>\n\n"
    
    for rank, (num, info) in enumerate(sorted_gan, 1):
        if info['last_date'] != "Trên 60 ngày":
            last_info = f"{info['last_date']} ({info['last_province']})"
        else:
            last_info = "Trên 60 ngày"
        msg += f"<b>{rank}. Bộ số {num}:</b> {info['days_gan']} ngày (Lần cuối: {last_info})\n"
        
    msg += f"\n⏰ <i>Cập nhật: {datetime.now().strftime('%H:%M %d/%m/%Y')}</i>"
    return msg

# ----------------------------------------------------
# HANDLERS & SCHEDULER
# ----------------------------------------------------
async def send_daily_report(app: Application):
    try:
        data = await calculate_lo_gan_async()
        report = format_report(data)
        await app.bot.send_message(chat_id=CHAT_ID, text=report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Lỗi gửi tin nhắn tự động: {e}")

async def checkgan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text("⏳ Đang cào dữ liệu và tính toán, vui lòng đợi...")
    try:
        sorted_gan = await calculate_lo_gan_async()
        report = format_report(sorted_gan)
        await wait_msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Lỗi /checkgan: {e}")
        await wait_msg.edit_text("❌ Lỗi cào dữ liệu. Vui lòng thử lại sau ít phút!")

def setup_scheduler(app: Application):
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    
    # Định thời 11:30 và 18:00
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(send_daily_report(app), app.loop), "cron", hour=11, minute=30)
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(send_daily_report(app), app.loop), "cron", hour=18, minute=0)
    scheduler.start()

# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("checkgan", checkgan_command))

    setup_scheduler(app)
    logger.info("Bot started successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
