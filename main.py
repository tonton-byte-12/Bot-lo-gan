import os
import threading
from datetime import datetime
import re
import bs4

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- WEB SERVER GIẢ LẬP ĐỂ RENDER WEB SERVICE DÙNG FREE ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot Lô Gan đang hoạt động 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- 1. Cấu hình Telegram ---
TOKEN = "8997592489:AAE8Ar60r1TBggUaexdzyC6c9E3veywivcI"
CHAT_ID = "-1004379710582"

# --- 2. Lịch 7 đài cố định chuẩn (Thứ 2 - 0 đến Chủ Nhật - 6) ---
LICH_DAI_XSMT = {
    0: {"ten": "Phú Yên", "ma": "phu-yen"},
    1: {"ten": "Đắk Lắk", "ma": "dak-lak"},
    2: {"ten": "Khánh Hòa", "ma": "khanh-hoa"},
    3: {"ten": "Quảng Trị", "ma": "quang-tri"},
    4: {"ten": "Gia Lai", "ma": "gia-lai"},
    5: {"ten": "Quảng Ngãi", "ma": "quang-ngai"},
    6: {"ten": "Kon Tum", "ma": "kon-tum"}
}

history_data = [
    {"ngay": "08/09/2026", "dai": "Đắk Lắk", "lo": ["01", "12", "55", "88"]},
    {"ngay": "09/09/2026", "dai": "Khánh Hòa", "lo": ["05", "23", "67", "90"]}
]

def get_kqxs_today():
    weekday = datetime.now().weekday()
    dai_info = LICH_DAI_XSMT[weekday]
    url = f"https://xskt.com.vn/{dai_info['ma']}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = bs4.BeautifulSoup(res.text, 'html.parser')
        table = soup.find('table', id='v-ketqua')
        if not table:
            return dai_info["ten"], []
            
        numbers = re.findall(r'\b\d{2,6}\b', table.text)
        lo_list = [num[-2:] for num in numbers if len(num) >= 2]
        return dai_info["ten"], list(set(lo_list))
    except Exception as e:
        print(f"Lỗi cào dữ liệu: {e}")
        return dai_info["ten"], []

def tao_noi_dung_tin_nhan():
    today_str = datetime.now().strftime("%d/%m/%Y")
    ten_dai, lo_hom_nay = get_kqxs_today()
    
    data_calc = list(history_data)
    if lo_hom_nay:
        data_calc.append({"ngay": today_str, "dai": ten_dai, "lo": lo_hom_nay})
        
    thong_ke_gan = []
    for i in range(100):
        so_str = f"{i:02d}"
        so_ngay_gan = 0
        ngay_gan_nhat = "Chưa rõ"
        
        for ngay_data in reversed(data_calc):
            if so_str in ngay_data["lo"]:
                ngay_gan_nhat = ngay_data["ngay"][:5]
                break
            else:
                so_ngay_gan += 1
                
        thong_ke_gan.append({
            "so": so_str,
            "so_ngay": so_ngay_gan,
            "ngay_gan_nhat": ngay_gan_nhat
        })
        
    thong_ke_gan.sort(key=lambda x: x["so_ngay"], reverse=True)
    top_5_gan = thong_ke_gan[:5]
    
    msg = f"🔔 *THỐNG KÊ LÔ GAN XSMT ({today_str})*\n"
    msg += f"🎯 *Đài hôm nay:* {ten_dai}\n\n"
    msg += "🔥 *Top cặp số lâu về nhất:*\n"
    
    for item in top_5_gan:
        msg += f"• *{item['so']}* — *{item['so_ngay']} ngày* _(Gần nhất: {item['ngay_gan_nhat']})_\n"
        
    if top_5_gan[0]["so_ngay"] >= 10:
        msg += f"\n⚠️ *Lưu ý:* Cặp số *{top_5_gan[0]['so']}* đã gan liên tiếp {top_5_gan[0]['so_ngay']} ngày chưa xuất hiện."
        
    return msg

def gui_tin_nhan_tu_dong():
    msg = tao_noi_dung_tin_nhan()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Đã gửi tin nhắn tự động thành công!")

async def handle_checkgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = tao_noi_dung_tin_nhan()
    await update.message.reply_text(msg, parse_mode="Markdown")

if __name__ == '__main__':
    # Chạy Web Server ở luồng phụ để Render nhận diện port
    threading.Thread(target=run_web, daemon=True).start()

    # Cài đặt lịch tự động 11h30, 15h30, 18h30
    scheduler = BackgroundScheduler()
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=11, minute=30)
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=15, minute=30)
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=18, minute=30)
    scheduler.start()
    
    # Khởi chạy Bot Telegram
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("checkgan", handle_checkgan))
    
    print("Bot đang chạy...")
    app.run_polling()
  
