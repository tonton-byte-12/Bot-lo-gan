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

# Ánh xạ slug URL chuẩn cho 7 đài XSMT cố định
SCHEDULE_MAP = {
    0: {"slug_mn": "phu-yen", "slug_xs": "phu-yen", "name": "Phú Yên"},
    1: {"slug_mn": "dak-lak", "slug_xs": "dak-lak", "name": "Đắk Lắk"},
    2: {"slug_mn": "khanh-hoa", "slug_xs": "khanh-hoa", "name": "Khánh Hòa"},
    3: {"slug_mn": "quang-tri", "slug_xs": "quang-tri", "name": "Quảng Trị"},
    4: {"slug_mn": "gia-lai", "slug_xs": "gia-lai", "name": "Gia Lai"},
    5: {"slug_mn": "quang-ngai", "slug_xs": "quang-ngai", "name": "Quảng Ngãi"},
    6: {"slug_mn": "kon-tum", "slug_xs": "kon-tum", "name": "Kon Tum"}
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CACHE_DATA = None
CACHE_TIME = None

# ----------------------------------------------------
# FLASK WEB SERVER
# ----------------------------------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "XSMT Bot Active", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ----------------------------------------------------
# THUẬT TOÁN CÀO KQXS CHUẨN XÁC THEO TỪNG ĐÀI
# ----------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def fetch_from_minhngoc(date_str, province_slug):
    """Cào chính xác 18 giải của DUY NHẤT 1 đài theo ngày trên MinhNgoc"""
    try:
        url = f"https://www.minhngoc.net.vn/ket-qua-xo-so/mien-trung/{province_slug}/{date_str}.html"
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            box = soup.find("table", class_="bkqtientien") or soup.find("table", class_="box_kqxs")
            if box:
                numbers = set()
                # Tìm tất cả ô chứa giải thưởng
                for td in box.find_all("td"):
                    txt = td.text.strip()
                    # Lấy các chuỗi số có độ dài từ 2 đến 6 chữ số
                    for match in re.findall(r"\b\d{2,6}\b", txt):
                        numbers.add(match[-2:])
                if len(numbers) >= 5: # Kết quả lô tô đầy đủ thường có từ 10-18 cặp số khác nhau
                    return list(numbers)
    except Exception as e:
        logger.warning(f"Lỗi MinhNgoc {province_slug} {date_str}: {e}")
    return None

def fetch_from_xosome(date_str, province_slug):
    """Nguồn dự phòng 2: Xoso.me"""
    try:
        url = f"https://xoso.me/kqxs-{province_slug}-ngay-{date_str}.html"
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            box = soup.find("table", class_="colgiai") or soup
            numbers = set()
            for span in box.find_all(["span", "div"], class_=re.compile(r"v-giai|number|duoc-ve", re.I)):
                txt = span.text.strip()
                if txt.isdigit() and len(txt) >= 2:
                    numbers.add(txt[-2:])
            if len(numbers) >= 5:
                return list(numbers)
    except Exception as e:
        logger.warning(f"Lỗi Xoso.me {province_slug} {date_str}: {e}")
    return None

def get_kqxs_exact(dt):
    date_str = dt.strftime("%d-%m-%Y")
    province = SCHEDULE_MAP[dt.weekday()]
    
    # Thử nguồn 1 (Minh Ngọc)
    data = fetch_from_minhngoc(date_str, province["slug_mn"])
    if not data:
        # Thử nguồn 2 (Xoso.me)
        data = fetch_from_xosome(date_str, province["slug_xs"])
        
    return data or [], province["name"]

# ----------------------------------------------------
# THUẬT TOÁN TÍNH GAN GỘP 60 NGÀY
# ----------------------------------------------------
async def calculate_lo_gan_async():
    global CACHE_DATA, CACHE_TIME
    
    # Trả về Cache nếu dữ liệu dưới 30 phút
    if CACHE_DATA and CACHE_TIME and (datetime.now() - CACHE_TIME).total_seconds() < 1800:
        return CACHE_DATA

    today = datetime.now().date()
    history = []

    # Quét chính xác 60 ngày quay gần nhất theo đúng lịch 7 đài
    for i in range(1, 61):
        target_date = today - timedelta(days=i)
        numbers, province_name = await asyncio.to_thread(get_kqxs_exact, target_date)
        history.append({
            "date": target_date,
            "province": province_name,
            "numbers": numbers
        })
        await asyncio.sleep(0.03)

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
    
    CACHE_DATA = sorted_gan
    CACHE_TIME = datetime.now()
    return sorted_gan

def format_report(sorted_gan):
    msg = "<b>🔥 THỐNG KÊ LÔ GAN GỘP ĐA ĐÀI - XSMT (60 NGÀY) 🔥</b>\n"
    msg += "<i>(Lịch 7 đài: PY->DLK->KH->QT->GL->QNG->KT)</i>\n\n"
    
    for rank, (num, info) in enumerate(sorted_gan, 1):
        if info['last_date'] != "Trên 60 ngày":
            last_info = f"{info['last_date']} ({info['last_province']})"
        else:
            last_info = "Trên 60 ngày"
        msg += f"<b>{rank}. Bộ số {num}:</b> Gan <b>{info['days_gan']}</b> ngày (Về gần nhất: {last_info})\n"
        
    msg += f"\n⏰ <i>Cập nhật: {datetime.now().strftime('%H:%M %d/%m/%Y')}</i>"
    return msg

# ----------------------------------------------------
# BOT HANDLERS & SCHEDULER
# ----------------------------------------------------
async def send_daily_report(app: Application):
    try:
        data = await calculate_lo_gan_async()
        report = format_report(data)
        await app.bot.send_message(chat_id=CHAT_ID, text=report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Lỗi gửi báo cáo tự động: {e}")

async def checkgan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text("⏳ Đang quét chính xác lịch sử 60 ngày gộp 7 đài XSMT, vui lòng đợi giây lát...")
    try:
        sorted_gan = await calculate_lo_gan_async()
        report = format_report(sorted_gan)
        await wait_msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Lỗi /checkgan: {e}")
        await wait_msg.edit_text("❌ Lỗi cào dữ liệu xổ số. Vui lòng thử lại sau!")

def setup_scheduler(app: Application, loop: asyncio.AbstractEventLoop):
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    
    # 11:30 sáng và 18:00 chiều
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(send_daily_report(app), loop), "cron", hour=11, minute=30)
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(send_daily_report(app), loop), "cron", hour=18, minute=0)
    scheduler.start()

# ----------------------------------------------------
# MAIN ENTRY POINT
# ----------------------------------------------------
async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("checkgan", checkgan_command))

    loop = asyncio.get_running_loop()
    setup_scheduler(app, loop)

    logger.info("Bot started successfully!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
