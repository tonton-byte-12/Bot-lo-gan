from datetime import datetime
import re
import bs4

from apscheduler.schedulers.background import BackgroundScheduler
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 1. Cấu hình Telegram
TOKEN = "8997592489:AAE8Ar60r1TBggUaexdzyC6c9E3veywivcI"
CHAT_ID = "-1004379710582"

# 2. Lịch 7 đài cố định chuẩn từ Thứ 2 (0) -> Chủ Nhật (6)
LICH_DAI_XSMT = {
    0: {"ten": "Phú Yên", "ma": "phu-yen"},  # Thứ 2
    1: {"ten": "Đắk Lắk", "ma": "dak-lak"},  # Thứ 3
    2: {"ten": "Khánh Hòa", "ma": "khanh-hoa"},  # Thứ 4
    3: {"ten": "Quảng Trị", "ma": "quang-tri"},  # Thứ 5
    4: {"ten": "Gia Lai", "ma": "gia-lai"},  # Thứ 6
    5: {"ten": "Quảng Ngãi", "ma": "quang-ngai"},  # Thứ 7
    6: {"ten": "Kon Tum", "ma": "kon-tum"},  # Chủ Nhật
}

# Giả lập CSDL lưu lịch sử (Nên dùng file JSON hoặc Database khi chạy lâu dài)
history_data = [
    {"ngay": "08/09/2026", "dai": "Đắk Lắk", "lo": ["01", "12", "55", "88"]},
    {"ngay": "09/09/2026", "dai": "Khánh Hòa", "lo": ["05", "23", "67", "90"]},
]


def get_kqxs_today():
    """Hàm cào 18 cặp số của đài trong ngày từ web xskt.com.vn"""
    weekday = datetime.now().weekday()
    dai_info = LICH_DAI_XSMT[weekday]
    url = f"https://xskt.com.vn/{dai_info['ma']}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = bs4.BeautifulSoup(res.text, "html.parser")
        table = soup.find("table", id="v-ketqua")
        if not table:
            return dai_info["ten"], []

        numbers = re.findall(r"\b\d{2,6}\b", table.text)
        lo_list = [num[-2:] for num in numbers if len(num) >= 2]
        return dai_info["ten"], list(set(lo_list))
    except Exception as e:
        print(f"Lỗi cào dữ liệu: {e}")
        return dai_info["ten"], []


def tao_noi_dung_tin_nhan():
    """Tạo nội dung thông báo lô gan theo Mẫu 1"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    ten_dai, lo_hom_nay = get_kqxs_today()

    # Tạo bản sao dữ liệu để tính toán
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

        thong_ke_gan.append(
            {"so": so_str, "so_ngay": so_ngay_gan, "ngay_gan_nhat": ngay_gan_nhat}
        )

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
    """Hàm gửi tự động vào Group Telegram"""
    msg = tao_noi_dung_tin_nhan()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload)
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] Đã gửi tin nhắn tự động thành công!"
    )


async def handle_checkgan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng gõ lệnh /checkgan"""
    msg = tao_noi_dung_tin_nhan()
    await update.message.reply_text(msg, parse_mode="Markdown")


if __name__ == "__main__":
    # 1. Đặt lịch tự động đúng 3 khung giờ: 11h30, 15h30, 18h30
    scheduler = BackgroundScheduler()
    scheduler.add_job(gui_tin_nhan_tu_dong, "cron", hour=11, minute=30)
    scheduler.add_job(gui_tin_nhan_tu_dong, "cron", hour=15, minute=30)
    scheduler.add_job(gui_tin_nhan_tu_dong, "cron", hour=18, minute=30)
    scheduler.start()

    # 2. Khởi chạy Bot lắng nghe lệnh /checkgan
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("checkgan", handle_checkgan))

    print("Bot đang chạy...")
    print("Lịch tự động: 11h30 | 15h30 | 18h30")
    print("Lệnh thủ công: /checkgan")
    app.run_polling()
