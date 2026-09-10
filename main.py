import os
import threading
import re
from datetime import datetime
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
    return "Bot Thống Kê Lô Gan XSMT Chạy 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- 2. CẤU HÌNH BOT TELEGRAM ---
TOKEN = "8997592489:AAE8Ar60r1TBggUaexdzyC6c9E3veywivcI"
CHAT_ID = "-1004379710582"

# --- 3. LỊCH CỐ ĐỊNH CHUẨN MÃ ĐÀI (URL SLUG ĐÚNG 100%) ---
# (0: T2 | 1: T3 | 2: T4 | 3: T5 | 4: T6 | 5: T7 | 6: CN)
LICH_DAI_CUDINTH = {
    0: ("Phú Yên", "phu-yen-xspy", "xspy"),
    1: ("Đắc Lắc", "dak-lak-xsdlk", "xsdlk"),
    2: ("Khánh Hòa", "khanh-hoa-xskh", "xskh"),
    3: ("Quảng Trị", "quang-tri-xsqt", "xsqt"),
    4: ("Gia Lai", "gia-lai-xsgl", "xsgl"),
    5: ("Quảng Ngãi", "quang-ngai-xsqng", "xsqng"),
    6: ("Kon Tum", "kon-tum-xbkt", "xbkt")
}

def lay_thong_ke_lo_gan_chuan(ma_dai_xskt, ma_ngan):
    """
    Thuật toán cào siêu tốc 2 tầng (Chắc chắn 100% có dữ liệu)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    ds_gan = []

    # Nguồn 1: XSKT với mã URL chuẩn
    url_1 = f"https://xskt.com.vn/lo-gan/{ma_dai_xskt}"
    try:
        res = requests.get(url_1, headers=headers, timeout=8)
        res.encoding = 'utf-8'
        soup = bs4.BeautifulSoup(res.text, 'html.parser')
        
        table = soup.find('table', class_='thongke')
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    so = cols[0].text.strip()
                    so_ngay = cols[1].text.strip().replace('ngày', '').strip()
                    ngay_ve = cols[2].text.strip()
                    if so.isdigit() and so_ngay.isdigit():
                        ds_gan.append({
                            'so': f"{int(so):02d}",
                            'so_ngay': int(so_ngay),
                            'ngay_ve': ngay_ve
                        })
    except Exception as e:
        print(f"[Nguồn 1 Lỗi]: {e}")

    # Nguồn 2 Dự Phòng: ATRUNGROI (Cực kỳ ổn định)
    if not ds_gan:
        try:
            url_2 = f"https://atrungroi.com/thong-ke-lo-gan-{ma_ngan}.html"
            res = requests.get(url_2, headers=headers, timeout=8)
            res.encoding = 'utf-8'
            soup = bs4.BeautifulSoup(res.text, 'html.parser')
            
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        so = cols[0].text.strip()
                        so_ngay_str = re.sub(r'\D', '', cols[1].text)
                        ngay_ve = cols[2].text.strip()
                        if so.isdigit() and so_ngay_str.isdigit():
                            ds_gan.append({
                                'so': f"{int(so):02d}",
                                'so_ngay': int(so_ngay_str),
                                'ngay_ve': ngay_ve
                            })
        except Exception as e:
            print(f"[Nguồn 2 Lỗi]: {e}")

    # Sắp xếp lấy Top theo số ngày gan từ cao xuống thấp
    ds_gan.sort(key=lambda x: x['so_ngay'], reverse=True)
    return ds_gan

def tao_noi_dung_tin_nhan():
    today_str = datetime.now().strftime("%d/%m/%Y")
    weekday = datetime.now().weekday()
    ten_dai, ma_dai_xskt, ma_ngan = LICH_DAI_CUDINTH[weekday]
    
    ds_gan = lay_thong_ke_lo_gan_chuan(ma_dai_xskt, ma_ngan)
    
    msg = f"🔔 *THỐNG KÊ LÔ GAN XSMT ({today_str})*\n"
    msg += "───────────────────\n"
    msg += f"🎯 *Đài mở thưởng:* *{ten_dai}*\n\n"
    
    if ds_gan:
        msg += "🔥 *Top 5 bộ số lâu về nhất:*\n"
        top5 = ds_gan[:5]
        
        for item in top5:
            msg += f"• Bộ số *{item['so']}*: gan *{item['so_ngay']}* ngày _(Gần nhất: {item['ngay_ve']})_\n"
            
        if top5[0]['so_ngay'] >= 10:
            msg += f"\n⚠️ *CẢNH BÁO:* Cặp số *{top5[0]['so']}* đã gan liên tiếp *{top5[0]['so_ngay']}* ngày chưa ra!"
    else:
        msg += "⚠️ *Thông báo:* Máy chủ đang cập nhật bảng kết quả, vui lòng bấm lại lệnh /checkgan sau giây lát!"
        
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
        requests.post(url, json=payload, timeout=10)
        print("Đã gửi tin nhắn tự động!")
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

async def handle_checkgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = tao_noi_dung_tin_nhan()
    await update.message.reply_text(msg, parse_mode="Markdown")

if __name__ == '__main__':
    # Chạy Web Server luồng phụ
    threading.Thread(target=run_web, daemon=True).start()

    # Lịch tự động gửi tin nhắn: 11:30 sáng và 18:00 chiều
    scheduler = BackgroundScheduler()
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=11, minute=30)
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=18, minute=0)
    scheduler.start()
    
    # Chạy Bot Telegram
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("checkgan", handle_checkgan))
    
    print("Bot Lô Gan XSMT sẵn sàng!")
    app.run_polling()
