
import ccxt
import csv
import requests
import time
from datetime import datetime
import os

# Cấu hình biến môi trường (sử dụng trên Render)
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
spreadsheet_url = os.getenv("SPREADSHEET_URL")

# Khởi tạo Binance Futures
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'options': {
        'defaultType': 'future'
    }
})

def fetch_csv_data():
    print("🟢 Đang tải dữ liệu từ Google Sheet CSV...")
    try:
        response = requests.get(spreadsheet_url)
        response.raise_for_status()
        lines = response.text.splitlines()
        reader = csv.reader(lines)
        data = list(reader)
        print(f"📊 Số dòng dữ liệu đọc được: {len(data)-1}")
        return data[1:]  # Bỏ dòng header
    except Exception as e:
        print("❌ Lỗi khi tải Google Sheet:", e)
        return []

def place_order(symbol, side, amount, sl_percent, tp_percent):
    print(f"🚀 Mở lệnh {side} {symbol} với {amount} USDT, SL: {sl_percent}%, TP: {tp_percent}%")
    try:
        markets = exchange.load_markets()
        symbol_clean = symbol.replace("-", "").upper()
        market = exchange.market(symbol_clean)
        price = market['info'].get('lastPrice')

        if price is None:
            print(f"⚠️ Không lấy được giá cho {symbol_clean}. Bỏ qua.")
            return

        price = float(price)
        sl_price = price * (1 - sl_percent / 100) if side == 'LONG' else price * (1 + sl_percent / 100)
        tp_price = price * (1 + tp_percent / 100) if side == 'LONG' else price * (1 - tp_percent / 100)
        order_side = 'buy' if side == 'LONG' else 'sell'

        exchange.create_order(
            symbol=symbol_clean,
            type='market',
            side=order_side,
            amount=amount / price,
            params={
                'stopPrice': sl_price,
                'takeProfitPrice': tp_price
            }
        )
        print(f"✅ Đã đặt lệnh {side} thành công.")
    except Exception as e:
        print(f"❌ Lỗi xử lý lệnh: [{symbol}, {side}] - {e}")

def main():
    print("🔁 Bắt đầu chạy script `main.py`")
    rows = fetch_csv_data()
    for row in rows:
        try:
            symbol = row[0].replace("-", "").upper()
            side = row[1].strip().upper()
            amount = float(row[2].replace("%", "").replace("USDT", "").strip())
            sl = float(row[3].replace("%", "").strip())
            tp = float(row[4].replace("%", "").strip())
            date = row[5]
            time_str = row[6]

            print(f"🔍 Đang kiểm tra coin {symbol} - Tín hiệu: {side}")
            if side not in ['LONG', 'SHORT']:
                print(f"⚠️ Bỏ qua tín hiệu không hợp lệ: {side}")
                continue

            place_order(symbol, side, amount, sl, tp)
        except Exception as e:
            print(f"❌ Lỗi xử lý dòng: {row} - {e}")

    print("✅ Đã hoàn tất chu kỳ. Đợi 60 phút để chạy lại.")

if __name__ == "__main__":
    main()
