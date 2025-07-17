import requests
import csv
import io
import logging
import time
import hmac
import hashlib
import base64
import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

# Cấu hình log
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# ===== THÔNG TIN BIẾN MÔI TRƯỜNG =====
API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
API_PASSPHRASE = os.getenv("OKX_PASSPHRASE")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")  # dạng CSV public

# ===== HÀM HỖ TRỢ =====
def get_timestamp():
    return datetime.utcnow().isoformat("T", "milliseconds") + "Z"

def sign(request_path, method, body, timestamp):
    message = f"{timestamp}{method}{request_path}{body}"
    mac = hmac.new(bytes(API_SECRET, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod=hashlib.sha256)
    d = mac.digest()
    return base64.b64encode(d).decode()

def place_order(symbol, side, size, sl_price, tp_price):
    try:
        logging.info(f"🟩 Mở lệnh {side} {symbol} với {size} USDT, SL: {sl_price*100:.1f}%, TP: {tp_price*100:.1f}%")

        url = "https://www.okx.com/api/v5/trade/order"
        timestamp = get_timestamp()
        body = {
            "instId": symbol,
            "tdMode": "isolated",
            "side": "buy" if side == "LONG" else "sell",
            "ordType": "market",
            "sz": str(size)
        }

        body_json = json.dumps(body)
        headers = {
            "OK-ACCESS-KEY": API_KEY,
            "OK-ACCESS-SIGN": sign("/api/v5/trade/order", "POST", body_json, timestamp),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": API_PASSPHRASE,
            "Content-Type": "application/json"
        }

        res = requests.post(url, headers=headers, data=body_json)
        logging.info(f"📤 Kết quả đặt lệnh: {res.status_code} - {res.text}")
        return res.status_code == 200
    except Exception as e:
        logging.error(f"❌ Lỗi khi đặt lệnh: {e}")
        return False

# ===== XỬ LÝ CHÍNH =====
def run_bot():
    try:
        logging.info("🚀 Bắt đầu chạy script main.py")

        # 1. Lấy dữ liệu từ Google Sheet (CSV public)
        logging.info("📥 Đang tải dữ liệu từ Google Sheet CSV")
        response = requests.get(SPREADSHEET_URL)
        response.raise_for_status()
        decoded_content = response.content.decode("utf-8")
        rows = list(csv.reader(io.StringIO(decoded_content)))
        rows = rows[1:]  # bỏ header

        logging.info(f"📊 Đã tải {len(rows)} tín hiệu từ Google Sheet")

        now = datetime.utcnow()
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

                created_at = datetime.strptime(created_at_str.strip(), "%Y-%m-%d %H-%m-%S")
                elapsed_minutes = (now - created_at).total_seconds() / 60

                if elapsed_minutes > interval:
                    logging.info(f"⏭ Bỏ qua lệnh quá hạn {symbol} - {signal}")
                    continue

                if signal not in ["LONG", "SHORT"]:
                    logging.warning(f"⚠️ Tín hiệu không hợp lệ: {signal}")
                    continue

                # 2. Gọi hàm đặt lệnh
                success = place_order(symbol, signal, 20, sl, tp)

                if success:
                    logging.info(f"✅ Đặt lệnh thành công cho {symbol}")
                else:
                    logging.warning(f"⚠️ Đặt lệnh thất bại cho {symbol}")

            except Exception as e:
                logging.error(f"❌ Lỗi xử lý dòng: {row} | Lỗi: {e}")

    except Exception as e:
        logging.error(f"❌ Lỗi tổng khi chạy bot: {e}")

if __name__ == "__main__":
    run_bot()
