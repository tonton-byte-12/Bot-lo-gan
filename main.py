import os
import threading
from datetime import datetime, timedelta
import requests
import bs4
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- 1. WEB SERVER DUY TRÌ RENDER RUN 24/7 ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot Thống Kê Lô Gan 7 Đài Miền Trung đang chạy!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- 2. CẤU HÌNH BOT TELEGRAM ---
TOKEN = "8997592489:AAE8Ar60r1TBggUaexdzyC6c9E3veywivcI"
CHAT_ID = "-1004379710582"

# Danh sách 7 đài bạn chọn tương ứng theo thứ trong tuần
# (0: T2 | 1: T3 | 2: T4 | 3: T5 | 4: T6 | 5: T7 | 6: CN)
DANH_SACH_7_DAI = {
    0: ("Phú Yên", "phu-yen-xspy"),
    1: ("Đắc Lắc", "dak-lak-xsdlk"),
    2: ("Khánh Hòa", "khanh-hoa-xskh"),
    3: ("Quảng Trị", "quang-tri-xsqt"),
    4: ("Gia Lai", "gia-lai-xsgl"),
    5: ("Quảng Ngãi", "quang-ngai-xsqng"),
    6: ("Kon Tum", "kon-tum-xbkt")
}

def lay_ket_qua_1_dai(slug_dai, date_str):
    """Cào kết quả lô 2 số của đúng 1 đài theo ngày"""
    url = f"https://xskt.com.vn/ket-qua-xo-so-theo-ngay/{slug_dai}/{date_str.replace('/', '-')}.html"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    lo_ve = set()
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.encoding = 'utf-8'
        soup = bs4.BeautifulSoup(res.text, 'html.parser')
        
        table = soup.find('table', class_='kqxs')
        if table:
            for td in table.find_all('td'):
                text = td.text.strip()
                if text.isdigit() and len(text) >= 2:
                    lo_ve.add(text[-2:])
    except Exception as e:
        print(f"Lỗi cào {slug_dai} ngày {date_str}: {e}")
        
    return lo_ve

def tinh_lo_gan_gop_7_dai(so_ngay_quet=60):
    """
    Thuật toán quét ngược lịch sử đúng 7 đài chọn lọc
    để tính số ngày gan chung cho 100 bộ số (00 - 99)
    """
    today = datetime.now()
    thong_ke_gan = {f"{i:02d}": {'so_ngay': so_ngay_quet, 'ngay_ve': 'Chưa ra', 'dai_ve': ''} for i in range(100)}
    
    # Quét ngược từng ngày trong quá khứ
    for i in range(so_ngay_quet):
        date_check = today - timedelta(days=i)
        weekday = date_check.weekday()
        
        # Lấy đài tương ứng của ngày đó trong danh sách 7 đài
        ten_dai, slug_dai = DANH_SACH_7_DAI[weekday]
        date_str = date_check.strftime("%d/%m/%Y")
        
        lo_ve_trong_ngay = lay_ket_qua_1_dai(slug_dai, date_str)
        
        # Cập nhật thông tin cho các bộ số chưa tìm thấy
        for so in list(thong_ke_gan.keys()):
            if thong_ke_gan[so]['ngay_ve'] == 'Chưa ra':
                if so in lo_ve_trong_ngay:
                    thong_ke_gan[so]['so_ngay'] = i
                    thong_ke_gan[so]['ngay_ve'] = date_str
                    thong_ke_gan[so]['dai_ve'] = ten_dai

    ds_kq = [{'so': k, 'so_ngay': v['so_ngay'], 'ngay_ve': v['ngay_ve'], 'dai_ve': v['dai_ve']} for k, v in thong_ke_gan.items()]
    ds_kq.sort(key=lambda x: x['so_ngay'], reverse=True)
    return ds_kq

def tao_noi_dung_tin_nhan():
    today_str = datetime.now().strftime("%d/%m/%Y")
    
    ds_gan = tinh_lo_gan_gop_7_dai(so_ngay_quet=60)
    
    msg = f"🔔 *THỐNG KÊ LÔ GAN GỘP 7 ĐÀI XSMT ({today_str})*\n"
    msg += "_(Phú Yên, Đắk Lắk, Khánh Hòa, Quảng Trị, Gia Lai, Quảng Ngãi, Kon Tum)_\n"
    msg += "───────────────────\n\n"
    
    msg += "🔥 *Top 10 bộ số lâu về nhất:* \n"
    top10 = ds_gan[:10]
    
    for item in top10:
        if item['ngay_ve'] != 'Chưa ra':
            msg += f"• Bộ số *{item['so']}*: gan *{item['so_ngay']}* ngày _(Lần cuối: {item['ngay_ve']} - Đài {item['dai_ve']})_\n"
        else:
            msg += f"• Bộ số *{item['so']}*: gan *>{item['so_ngay']}* ngày chưa ra\n"
            
    return msg

def gui_tin_nhan_tu_dong():
    msg = tao_noi_dung_tin_nhan()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=20)
        print("Đã gửi tin nhắn lô gan gộp thành công!")
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

async def handle_checkgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Đang quét dữ liệu lịch sử 7 đài Miền Trung, vui lòng chờ khoảng 5-8 giây...")
    msg = tao_noi_dung_tin_nhan()
    await update.message.reply_text(msg, parse_mode="Markdown")

if __name__ == '__main__':
    # Chạy Web Server luồng phụ
    threading.Thread(target=run_web, daemon=True).start()

    # Lịch tự động gửi tin nhắn 11:30 và 18:00 hằng ngày
    scheduler = BackgroundScheduler()
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=11, minute=30)
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=18, minute=0)
    scheduler.start()
    
    # Khởi chạy Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("checkgan", handle_checkgan))
    
    print("Bot Lô Gan Gộp 7 Đài Miền Trung đã sẵn sàng!")
    app.run_polling()
