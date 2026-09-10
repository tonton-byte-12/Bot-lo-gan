import os
import threading
from datetime import datetime
import requests
import bs4
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- 1. WEB SERVER DÙNG DUY TRÌ BẢN FREE TRÊN RENDER ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot Thống Kê Lô Gan XSMT đang hoạt động 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- 2. CẤU HÌNH BOT TELEGRAM ---
TOKEN = "8997592489:AAE8Ar60r1TBggUaexdzyC6c9E3veywivcI"
CHAT_ID = "-1004379710582"

# --- 3. LỊCH CÁC ĐÀI CỐ ĐỊNH THEO YÊU CẦU ---
# (0: Thứ 2 | 1: Thứ 3 | 2: Thứ 4 | 3: Thứ 5 | 4: Thứ 6 | 5: Thứ 7 | 6: Chủ Nhật)
LICH_DAI_CUDINTH = {
    0: ("Phú Yên", "phu-yen"),
    1: ("Đắk Lắk", "dak-lak"),
    2: ("Khánh Hòa", "khanh-hoa"),
    3: ("Quảng Trị", "quang-tri"),
    4: ("Gia Lai", "gia-lai"),
    5: ("Quảng Ngãi", "quang-ngai"),
    6: ("Kon Tum", "kon-tum")
}

def lay_thong_ke_lo_gan_manh(ma_dai):
    """
    Thuật toán cào đa tầng (Fallback Engine)
    Quét và trích xuất bảng lô gan chính xác 100%
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    ds_gan = []

    # Nguồn 1: XSKT Thống kê Lô Gan chuyên sâu
    url_1 = f"https://xskt.com.vn/lo-gan/{ma_dai}"
    try:
        res = requests.get(url_1, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = bs4.BeautifulSoup(res.text, 'html.parser')
        
        table = soup.find('table', class_='thongke')
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    so = cols[0].text.strip()
                    so_ngay_raw = cols[1].text.strip().replace('ngày', '').strip()
                    ngay_ve = cols[2].text.strip()
                    
                    if so.isdigit() and so_ngay_raw.isdigit():
                        ds_gan.append({
                            'so': f"{int(so):02d}",
                            'so_ngay': int(so_ngay_raw),
                            'ngay_ve': ngay_ve
                        })
    except Exception as e:
        print(f"[Nguồn 1] Lỗi cào đài {ma_dai}: {e}")

    # Nguồn 2 Dự phòng: Minh Ngọc Lô Gan (Nhiệm vụ Fallback khi Nguồn 1 gián đoạn)
    if not ds_gan:
        try:
            url_2 = f"https://www.minhngoc.com.vn/thong-ke-lo-gan/{ma_dai}.html"
            res = requests.get(url_2, headers=headers, timeout=10)
            res.encoding = 'utf-8'
            soup = bs4.BeautifulSoup(res.text, 'html.parser')
            
            tables = soup.find_all('table', class_='bkqua')
            for tb in tables:
                rows = tb.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        so = cols[0].text.strip()
                        so_ngay_raw = cols[1].text.strip()
                        ngay_ve = cols[2].text.strip()
                        
                        if so.isdigit() and so_ngay_raw.isdigit():
                            ds_gan.append({
                                'so': f"{int(so):02d}",
                                'so_ngay': int(so_ngay_raw),
                                'ngay_ve': ngay_ve
                            })
        except Exception as e:
            print(f"[Nguồn 2] Lỗi cào đài {ma_dai}: {e}")

    # Lọc trùng lặp & Sắp xếp theo số ngày gan từ cao xuống thấp
    seen = set()
    ds_gan_clean = []
    for item in ds_gan:
        if item['so'] not in seen:
            seen.add(item['so'])
            ds_gan_clean.append(item)
            
    ds_gan_clean.sort(key=lambda x: x['so_ngay'], reverse=True)
    return ds_gan_clean

def tao_noi_dung_tin_nhan():
    today_str = datetime.now().strftime("%d/%m/%Y")
    weekday = datetime.now().weekday()
    ten_dai, ma_dai = LICH_DAI_CUDINTH[weekday]
    
    ds_gan = lay_thong_ke_lo_gan_manh(ma_dai)
    
    msg = f"🔔 *THỐNG KÊ LÔ GAN XSMT ({today_str})*\n"
    msg += "───────────────────\n"
    msg += f"🎯 *Đài mở thưởng:* *{ten_dai}*\n\n"
    
    if ds_gan:
        msg += "🔥 *Top 5 bộ số lâu về nhất:*\n"
        top5 = ds_gan[:5]
        
        for item in top5:
            msg += f"• Bộ số *{item['so']}*: gan *{item['so_ngay']}* ngày _(Gần nhất: {item['ngay_ve']})_\n"
            
        if top5[0]['so_ngay'] >= 10:
            msg += f"\n⚠️ *CẢNH BÁO GAN SÂU:* Cặp số *{top5[0]['so']}* đã gan liên tiếp *{top5[0]['so_ngay']}* ngày chưa ra!"
    else:
        msg += "⚠️ *Thông báo:* Hệ thống máy chủ xổ số đang cập nhật dữ liệu mới. Vui lòng bấm lệnh /checkgan lại sau ít phút!"
        
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Đã gửi thông báo lô gan tự động!")
    except Exception as e:
        print(f"Lỗi gửi tin nhắn Telegram: {e}")

async def handle_checkgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = tao_noi_dung_tin_nhan()
    await update.message.reply_text(msg, parse_mode="Markdown")

if __name__ == '__main__':
    # 1. Chạy Flask Web Server ở luồng phụ duy trì kết nối Render 24/7
    threading.Thread(target=run_web, daemon=True).start()

    # 2. Đặt lịch gửi tin nhắn tự động 2 khung giờ trong ngày:
    # 11:30 Sáng (Soi lô trước giờ quay) & 18:00 Tối (Sau khi đài miền Trung quay xong)
    scheduler = BackgroundScheduler()
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=11, minute=30)
    scheduler.add_job(gui_tin_nhan_tu_dong, 'cron', hour=18, minute=0)
    scheduler.start()
    
    # 3. Lắng nghe lệnh từ Telegram
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("checkgan", handle_checkgan))
    
    print("Bot Thống Kê Lô Gan XSMT đã kích hoạt thành công!")
    app.run_polling()
