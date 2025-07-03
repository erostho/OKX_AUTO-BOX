
import requests
import ccxt
import pandas as pd
import json
import time
import hmac
import base64
import hashlib
from datetime import datetime, timedelta
import os

# Thiết lập thông tin API OKX từ biến môi trường
API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
API_PASSPHRASE = os.getenv("OKX_PASSPHRASE")

# Thiết lập đường dẫn sheet CSV công khai
sheet_url = "https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/export?format=csv"
df = pd.read_csv(sheet_url)

# Chuẩn hoá dữ liệu và lọc theo điều kiện
df = df.dropna()
df['Thời gian'] = pd.to_datetime(df['Thời gian'], format="%d/%m/%Y %H:%M:%S")
now = datetime.now()
df = df[df['Thời gian'] > now - timedelta(minutes=60)]
df = df[df['Xu hướng'].str.upper().isin(["TĂNG MẠNH", "GIẢM MẠNH"])]

# Khởi tạo ccxt để lấy giá coin từ OKX
exchange = ccxt.okx()

for _, row in df.iterrows():
    try:
        coin = row['Coin'].replace("-USDT", "/USDT").upper()
        inst_id = row['Coin'].replace("-", "").upper()
        side = "long" if row['Xu hướng'].strip().upper() == "TĂNG MẠNH" else "short"

        # Lấy giá hiện tại
        ticker = exchange.fetch_ticker(coin)
        price = ticker['last']
        lower_price = round(price * 0.85, 4)
        upper_price = round(price * 1.15, 4)

        # Tạo payload
        payload = {
            "instId": inst_id,
            "algoType": "grid",
            "minPx": lower_price,
            "maxPx": upper_price,
            "gridNum": 20,
            "lever": "5",
            "direction": side,
            "investment": "10"
        }

        body = json.dumps(payload)
        timestamp = str(time.time())
        method = "POST"
        request_path = "/api/v5/tradingBot/grid/orderAlgo"
        message = timestamp + method + request_path + body

        signature = base64.b64encode(
            hmac.new(API_SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
        ).decode()

        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": API_KEY,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": API_PASSPHRASE
        }

        # In log tạo bot (có thể thay bằng requests.post nếu muốn gọi thật)
        print(f"Tạo bot cho {inst_id}: {side.upper()} tại giá {price} | Vùng {lower_price} - {upper_price}")
        response = requests.post("https://www.okx.com" + request_path, headers=headers, data=body)
        print(response.json())

    except Exception as e:
        print(f"⚠️ Lỗi khi xử lý {row['Coin']}: {e}")
