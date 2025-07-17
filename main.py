
import os
import requests
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# Cấu hình log
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# Lấy biến môi trường
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_API_SECRET = os.getenv("OKX_API_SECRET")
OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")

# Hàm tạo chữ ký OKX
def create_okx_headers(api_key, api_secret, passphrase, method, endpoint, body=""):
    import base64, hmac, hashlib
    timestamp = str(int(time.time()))
    prehash = timestamp + method + endpoint + body
    sign = base64.b64encode(hmac.new(api_secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
    return {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json"
    }

# Hàm đặt đòn bẩy 5x
def set_leverage(symbol, leverage):
    instId = symbol.upper().replace('-', '-')
    endpoint = f"/api/v5/account/set-leverage"
    url = "https://www.okx.com" + endpoint
    body = {
        "instId": instId,
        "lever": str(leverage),
        "mgnMode": "isolated"
    }
    import json
    headers = create_okx_headers(OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE, "POST", endpoint, json.dumps(body))
    res = requests.post(url, headers=headers, json=body)
    logging.info(f"⚙️ Set đòn bẩy {leverage}x cho {symbol} | Trạng thái: {res.status_code} | Trả về: {res.text}")
    return res.status_code == 200

# Hàm xử lý tín hiệu
def run_bot():
    import re
    try:
        sheet = gspread.service_account().open_by_url(SPREADSHEET_URL).worksheet("DATA_12H")
        rows = sheet.get_all_values()[1:]
        logging.info(f"📥 Đã tải {len(rows)} tín hiệu từ Google Sheet")
    except Exception as e:
        logging.error(f"Không thể tải dữ liệu Google Sheet: {e}")
        return

    now = datetime.utcnow()
    for row in rows:
        try:
            if len(row) < 7:
                logging.warning(f"⚠️ Bỏ qua dòng thiếu dữ liệu: {row}")
                continue
            symbol, signal, price_str, sl_str, tp_str, date_str, interval = row
            entry_price = float(price_str)
            sl = float(sl_str.strip('%')) / 100
            tp = float(tp_str.strip('%')) / 100
            interval = int(interval)
            created_at = datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S")
            minutes_passed = (now - created_at).total_seconds() / 60
            if minutes_passed > interval:
                logging.info(f"⏰ Bỏ qua tín hiệu quá hạn cho {symbol}")
                continue

            if signal not in ["LONG", "SHORT"]:
                logging.warning(f"⚠️ Tín hiệu không hợp lệ: {signal}")
                continue

            # Set đòn bẩy 5x
            set_leverage(symbol, 5)

            # Gửi log đặt lệnh (mockup - vì không gọi real order ở đây)
            logging.info(f"✅ Mở lệnh {signal} {symbol} với {entry_price} USDT, SL: {sl*100:.1f}%, TP: {tp*100:.1f}%")

        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {row} | {e}")

# Chạy
if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")
    run_bot()
