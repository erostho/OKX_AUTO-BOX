
import requests
import pandas as pd
import time
import hmac
import hashlib
import os
import urllib.parse

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
SPREADSHEET_URL = os.getenv('SPREADSHEET_URL')  # Public Google Sheet CSV URL

BASE_URL = 'https://fapi.binance.com'

def get_data_from_sheet():
    df = pd.read_csv(SPREADSHEET_URL)
    df = df.dropna(subset=['Coin', 'Xu hướng', 'Thời gian'])
    return df

def get_current_price(symbol):
    url = f"{BASE_URL}/fapi/v1/ticker/price?symbol={symbol}"
    res = requests.get(url)
    return float(res.json()['price'])

def place_future_order(symbol, side, quantity, entry_price):
    timestamp = int(time.time() * 1000)
    recvWindow = 5000
    endpoint = "/fapi/v1/order"

    order_data = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": quantity,
        "timestamp": timestamp,
        "recvWindow": recvWindow
    }

    query_string = urllib.parse.urlencode(order_data)
    signature = hmac.new(BINANCE_API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    order_data["signature"] = signature

    headers = {
        "X-MBX-APIKEY": BINANCE_API_KEY
    }

    response = requests.post(BASE_URL + endpoint, headers=headers, params=order_data)
    print(response.json())
    return response.json()

def main():
    df = get_data_from_sheet()
    now = pd.Timestamp.now()

    for index, row in df.iterrows():
        try:
            symbol = row['Coin'].replace('-USDT', 'USDT').upper()
            direction = row['Xu hướng'].strip().upper()
            last_time = pd.to_datetime(row['Thời gian'], dayfirst=True)
            minutes_diff = (now - last_time).total_seconds() / 60

            if direction in ['TĂNG MẠNH', 'GIẢM MẠNH'] and minutes_diff <= 60:
                side = 'BUY' if direction == 'TĂNG MẠNH' else 'SELL'
                price = get_current_price(symbol)
                quantity = round(20 / price, 3)  # 20 USDT mỗi lệnh

                print(f"📌 Đặt lệnh {side} {symbol} với giá {price}, SL/TP tự xử lý sau")
                place_future_order(symbol, side, quantity, price)
        except Exception as e:
            print(f"Lỗi xử lý dòng {index}: {e}")

if __name__ == "__main__":
    main()
