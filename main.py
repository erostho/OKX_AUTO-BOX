
import os
import requests
import csv
import time
import hmac
import hashlib

# Log start
print("🚀 Bắt đầu chạy script 'main.py'")

# Get environment variables
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")

print("✅ Đang tải dữ liệu từ Google Sheet CSV")

# Download and parse CSV data
response = requests.get(SPREADSHEET_URL)
lines = response.text.splitlines()
reader = csv.reader(lines)
data = list(reader)

print(f"📊 Số dòng dữ liệu đọc được: {len(data)}")

# Skip header
for row in data[1:]:
    try:
        coin, signal, timestamp = row[0], row[1].upper(), row[2]
        symbol = coin.upper() + "USDT"
        print(f"🔍 Đang kiểm tra coin {symbol} - Tín hiệu: {signal}")

        if signal not in ["LONG", "SHORT"]:
            print(f"⚠️ Bỏ qua tín hiệu không hợp lệ: {signal}")
            continue

        # Fetch current price
        ticker_url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
        price_res = requests.get(ticker_url)
        current_price = float(price_res.json()["price"])
        print(f"💰 Giá hiện tại {symbol}: {current_price}")

        # Calculate TP/SL
        qty = round(20 / current_price, 3)
        tp_price = round(current_price * 1.15, 2) if signal == "LONG" else round(current_price * 0.85, 2)
        sl_price = round(current_price * 0.9, 2) if signal == "LONG" else round(current_price * 1.1, 2)
        side = "BUY" if signal == "LONG" else "SELL"

        print(f"📤 Gửi lệnh {signal} {symbol}, khối lượng: {qty}")
        print(f"⛔ SL: {sl_price}, 🎯 TP: {tp_price}")

        # Place market order
        base_url = "https://fapi.binance.com"
        endpoint = "/fapi/v1/order"
        timestamp = int(time.time() * 1000)
        query = f"symbol={symbol}&side={side}&type=MARKET&quantity={qty}&timestamp={timestamp}"
        signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{base_url}{endpoint}?{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        order_res = requests.post(url, headers=headers)
        print(f"✅ Lệnh thị trường: {order_res.status_code} - {order_res.text}")

        # TP/SL đặt bằng OCO hoặc lệnh điều kiện
        # Gửi thêm log nếu cần

    except Exception as e:
        print(f"❌ Lỗi xử lý dòng: {row} | Lỗi: {e}")

print("✅ Đã hoàn tất chu kỳ. Đợi 60 phút để chạy lại.")
