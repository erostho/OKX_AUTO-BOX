import csv
import os
import requests
import logging
from datetime import datetime
import ccxt

# Cấu hình log
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# Lấy biến môi trường
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_API_SECRET = os.getenv("OKX_API_SECRET")
OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")

# Khởi tạo kết nối OKX
exchange = ccxt.okx({
    "apiKey": OKX_API_KEY,
    "secret": OKX_API_SECRET,
    "password": OKX_API_PASSPHRASE,
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap"
    }
})

def download_csv(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def parse_csv(text):
    rows = []
    reader = csv.reader(text.strip().split("\n"))
    next(reader)  # bỏ dòng tiêu đề
    for row in reader:
        if len(row) >= 7:
            rows.append(row)
    return rows

def run_bot():
    now = datetime.utcnow()
    try:
        logging.info("📥 Bắt đầu chạy script main.py")
        csv_text = download_csv(SPREADSHEET_URL)
        rows = parse_csv(csv_text)
        logging.info(f"📊 Đã tải {len(rows)} tín hiệu từ Google Sheet")
    except Exception as e:
        logging.error(f"❌ Không thể tải dữ liệu Google Sheet: {e}")
        return

    for row in rows:
        try:
            logging.info(f"🔍 Đang kiểm tra dòng: {row}")
            if len(row) < 7:
                logging.warning(f"⚠️ Bỏ qua dòng không đủ 7 cột: {row}")
                continue

            symbol, signal, entry_price, sl_str, tp_str, created_at_str, interval = row

            # Ép kiểu
            entry_price = float(entry_price)
            sl = float(sl_str.strip('%')) / 100
            tp = float(tp_str.strip('%')) / 100
            interval = int(interval)

            created_at = datetime.strptime(created_at_str.strip(), "%Y-%m-%d %H:%M:%S")
            elapsed_minutes = (now - created_at).total_seconds() / 60

            if elapsed_minutes > interval:
                logging.info(f"⏩ Bỏ qua lệnh quá hạn cho {symbol} - {signal}")
                continue

            if signal not in ["LONG", "SHORT"]:
                logging.warning(f"⚠️ Bỏ qua tín hiệu không hợp lệ: {signal}")
                continue

            # Thiết lập đòn bẩy 5x
            try:
                exchange.set_leverage(5, symbol)
                logging.info(f"🎯 Đã thiết lập đòn bẩy 5x cho {symbol}")
            except Exception as e:
                logging.warning(f"⚠️ Không thể thiết lập đòn bẩy cho {symbol}: {e}")

            usdt_amount = 20
            mark_price = exchange.fetch_ticker(symbol)['last']
            amount = round(usdt_amount / mark_price, 4)

            logging.info(f"🟢 Mở lệnh {signal} {symbol} với {usdt_amount} USDT, SL: {sl*100}%, TP: {tp*100}%")

            if signal == "LONG":
                order = exchange.create_market_buy_order(symbol, amount)
            else:
                order = exchange.create_market_sell_order(symbol, amount)

            logging.info(f"✅ Đặt lệnh thành công cho {symbol}: {signal}")
        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {row} | Lỗi: {e}")

if __name__ == "__main__":
    run_bot()
