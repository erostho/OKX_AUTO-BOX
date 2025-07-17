
import requests
import time
import hmac
import base64
import json
import logging
import os
from datetime import datetime, timedelta
from urllib.parse import urljoin

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ENV variables
API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")

BASE_URL = "https://www.okx.com"

# Request headers for OKX API
def get_headers(timestamp, method, request_path, body=""):
    message = f"{timestamp}{method.upper()}{request_path}{body}"
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode(), message.encode(), digestmod="sha256").digest()
    ).decode()
    return {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": API_PASSPHRASE,
        "Content-Type": "application/json"
    }

# Place future order
def place_future_order(symbol, side, size, sl_price, tp_price):
    timestamp = datetime.utcnow().isoformat("T", "milliseconds") + "Z"
    request_path = "/api/v5/trade/order"
    url = urljoin(BASE_URL, request_path)
    order_data = {
        "instId": symbol,
        "tdMode": "isolated",
        "side": side.lower(),
        "ordType": "market",
        "posSide": side.upper(),
        "sz": str(size)
    }
    headers = get_headers(timestamp, "POST", request_path, json.dumps(order_data))
    response = requests.post(url, headers=headers, json=order_data)
    logging.info(f"Gửi lệnh {side} {symbol} với {size} USDT")
    if response.status_code != 200:
        logging.error(f"Lỗi API: {response.text}")
    else:
        logging.info(f"Phản hồi: {response.text}")

# Load Google Sheet CSV
def fetch_signals():
    try:
        res = requests.get(SPREADSHEET_URL)
        rows = [r.split(",") for r in res.text.strip().split("\n")]
        return rows[1:]  # Skip header
    except Exception as e:
        logging.error(f"Lỗi tải sheet: {e}")
        return []

# Get latest price from OKX
def get_latest_price(symbol):
    url = f"{BASE_URL}/api/v5/market/ticker?instId={symbol}"
    res = requests.get(url).json()
    try:
        return float(res["data"][0]["last"])
    except:
        return None

# Main handler
def main():
    signals = fetch_signals()
    logging.info(f"📊 Đã tải {len(signals)} tín hiệu từ Google Sheet")

    for s in signals:
        try:
            symbol = s[0].strip()
            signal = s[1].strip().upper()
            price = float(s[2])
            sl = float(s[3].replace("%", "")) / 100
            tp = float(s[4].replace("%", "")) / 100
            time_str = s[5].strip()
            freq = int(s[6]) if len(s) > 6 else 60

            # Check time range
            timestamp = datetime.strptime(time_str, "%Y-%m-%d")
            if datetime.now() - timestamp > timedelta(minutes=freq):
                continue

            logging.info(f"🔍 Đang kiểm tra {symbol} – Tín hiệu: {signal}")

            current_price = get_latest_price(symbol)
            if not current_price:
                logging.warning(f"⚠️ Không lấy được giá cho {symbol}")
                continue

            sl_price = current_price * (1 - sl) if signal == "LONG" else current_price * (1 + sl)
            tp_price = current_price * (1 + tp) if signal == "LONG" else current_price * (1 - tp)

            place_future_order(symbol, signal, 20, sl_price, tp_price)
        except Exception as e:
            logging.error(f"Lỗi xử lý {s}: {e}")

if __name__ == "__main__":
    main()
