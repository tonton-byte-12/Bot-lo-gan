import os
import re
import time
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

# Ánh xạ đài cố định theo ngày trong tuần (weekday: 0=Thứ 2, ..., 6=Chủ nhật)
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

# ----------------------------------------------------
# FLASK WEB SERVER (Dùng duy trì ping 24/7 trên Render)
# ----------------------------------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "XSMT Lo Gan Bot is running live!", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ----------------------------------------------------
# CÀO DỮ LIỆU KQXS - DỰ PHÒNG ĐA TẦNG (FALLBACK ENGINE)
# ----------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_from_source_1(date_str, province_code):
    """Nguồn 1: Minh Ngọc (minhngoc.net.vn)"""
    try:
        url = f"https://www.minhngoc.net.vn/ket-qua-xo-so/mien-trung/{date_str}.html"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            box = soup.find("div", class_=re.compile(f".*{province_code}.*", re.I))
            if not box:
                box = soup
            numbers = set()
            for td in box.find_all(["td", "div"], class_=re.compile(r"giai|so", re.I)):
                txt = td.text.strip()
                found = re.findall(r"\b\d{2,6}\b", txt)
                for num in found:
                    numbers.add(num[-2:])
            if len(numbers) >= 10:
                return list(numbers)
    except Exception as e:
        logger.warning(f"Nguồn 1 lỗi ngày {date_str}: {e}")
    return None

def fetch_from_source_2(date_str, province_code):
    """Nguồn 2: Xoso.me"""
    try:
        parts = date_str.split("-")
        formatted_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
        url = f"https://xoso.me/kqxs-mien-trung-ngay-{formatted_date}.html"
        resp = requests.get(url, headers=HEADERS, timeout=8)
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
        logger.warning(f"Nguồn 2 lỗi ngày {date_str}: {e}")
    return None

def get_kqxs_by_date(dt):
    """Gọi đa tầng nguồn cào KQXS"""
    date_str = dt.strftime("%d-%m-%Y")
    province_info = SCHEDULE_MAP[dt.weekday()]
    
    # Thử nguồn 1
    data = fetch_from_source_1(date_str, province_info["code"])
    if data:
        return data, province_info["name"]
        
    # Thử nguồn 2 nếu nguồn 1 thất bại
    data = fetch_from_source_2(date_str, province_info["code"])
    if data:
        return data, province_info["name"]
        
    return [], province_info["name"]

# ----------------------------------------------------
# THUẬT TOÁN TÍNH LÔ GAN GỘP ĐA ĐÀI (60 NGÀY)
# ----------------------------------------------------
def calculate_lo_gan():
    today = datetime.now().date()
    history = []

    # Quét ngược 60 ngày gần nhất
    for i in range(1, 61):
        target_date = today - timedelta(days=i)
        numbers, province_name = get_kqxs_by_date(target_date)
        history.append({
            "date": target_date,
            "province": province_name,
            "numbers": numbers
        })
        time.sleep(0.1) # Tránh bị chặn IP

    gan_dict = {}
    
    for num in range(100):
        num_str = f"{num:02d}"
        days_gan = 0
        last_date = None
        last_province = "Chưa xuất hiện"
        
        for idx, day_data in enumerate(history):
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

    # Sắp xếp lấy Top 10 bộ số lô gan lâu xuất hiện nhất
    sorted_gan = sorted(gan_dict.items(), key=lambda x: x[1]["days_gan"], reverse=True)[:10]
    return sorted_gan

def format_report(sorted_gan):
    msg = "🔥 **THỐNG KÊ LÔ GAN GỘP ĐA ĐÀI - XSMT (60 NGÀY)** 🔥\n"
    msg += "*(Tự động quét theo lịch 7 đài cố định)*\n\n"
    msg += "-----------------------------------------\n"
    msg += f"{'Bộ số':<6} | {'Số ngày gan':<12} | {'Lần cuối về':<20}\n"
    msg += "-----------------------------------------\n"
    
    for rank, (num, info) in enumerate(sorted_gan, 1):
        last_info = f"{info['last_date']} ({info['last_province']})" if info['last_date'] != "Trên 60 ngày" else "Trên 60 ngày"
        msg += f"**{num}**    | {info['days_gan']} ngày      | {last_info}\n"
        
    msg += "-----------------------------------------\n"
    msg += f"⏰ *Cập nhật lúc:* {datetime.now().strftime('%H:%M %d/%m/%Y')}"
    return msg

# ----------------------------------------------------
# SCHEDULER & TELEGRAM BOT HANDLERS
# ----------------------------------------------------
async def send_daily_report(app: Application):
    try:
        report = format_report(calculate_lo_gan())
        await app.bot.send_message(chat_id=CHAT_ID, text=report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Lỗi gửi tin nhắn tự động: {e}")

async def checkgan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text("⏳ Đang cào dữ liệu và tính toán lô gan gộp 7 đài trong 60 ngày, vui lòng đợi trong giây lát...")
    try:
        sorted_gan = calculate_lo_gan()
        report = format_report(sorted_gan)
        await wait_msg.edit_text(report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Lỗi khi xử lý /checkgan: {e}")
        await wait_msg.edit_text("❌ Có lỗi xảy ra trong quá trình tính toán. Vui lòng thử lại sau!")

def setup_scheduler(app: Application):
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    
    # Khung giờ 1: 11:30 AM
    scheduler.add_job(
        lambda: app.create_task(send_daily_report(app)),
        "cron", hour=11, minute=30
    )
    # Khung giờ 2: 18:00 PM
    scheduler.add_job(
        lambda: app.create_task(send_daily_report(app)),
        "cron", hour=18, minute=0
    )
    scheduler.start()

# ----------------------------------------------------
# MAIN ENTRY POINT
# ----------------------------------------------------
def main():
    # Chạy Web Server Flask trên thread riêng
    threading.Thread(target=run_flask, daemon=True).start()

    # Khởi tạo Telegram Bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("checkgan", checkgan_command))

    # Khởi chạy Scheduler
    setup_scheduler(app)

    logger.info("Bot đã khởi chạy thành công!")
    app.run_polling()

if __name__ == "__main__":
    main()
