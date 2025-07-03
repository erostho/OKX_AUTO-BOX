import requests
import ccxt
import pandas as pd
import json
import time
from datetime import datetime, timedelta
import os

# Thiết lập thông tin API OKX
API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
API_PASSPHRASE = os.getenv("OKX_PASSPHRASE")
body = json.dumps(payload)
# Thiết lập headers cho API OKX
timestamp = str(time.time())
method = "POST"
request_path = "/api/v5/tradingBot/grid/orderAlgo"

message = timestamp + method + request_path + body
signature = base64.b64encode(
    hmac.new(API_SECRET.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
).decode()

headers = {
    'Content-Type': 'application/json',
    'OK-ACCESS-KEY': API_KEY,
    'OK-ACCESS-SIGN': signature,
    'OK-ACCESS-TIMESTAMP': timestamp,
    'OK-ACCESS-PASSPHRASE': API_PASSPHRASE
}

# Đọc dữ liệu từ Google Sheet public CSV
sheet_url = 'https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/gviz/tq?tqx=out:csv&sheet=DATA_12H'
df = pd.read_csv(sheet_url)

# Chuẩn hoá dữ liệu và lọc theo điều kiện, Thêm năm hiện tại vào chuỗi thời gian
df = df.dropna()
current_year = datetime.now().year
df['Thời gian'] = df['Thời gian'].apply(lambda x: f"{current_year}/{x.strip()}")
df['Thời gian'] = pd.to_datetime(df['Thời gian'], format='%Y/%d/%m %H:%M')
df = df[df['Xu hướng'].str.upper().isin(['TĂNG MẠNH', 'GIẢM MẠNH'])]

# Khởi tạo ccxt để lấy giá
exchange = ccxt.okx()
symbols = df['Coin'].tolist()

for index, row in df.iterrows():
    coin = row['Coin'].replace('-USDT', '/USDT').upper()
    side = 'long' if row['Xu hướng'].upper() == 'TĂNG MẠNH' else 'short'
    try:
        ticker = exchange.fetch_ticker(coin)
        price = ticker['last']
        lower_price = round(price * 0.85, 4)
        upper_price = round(price * 1.15, 4)

        # Payload tạo Grid Bot đơn giản (cần API OKX hỗ trợ)
        payload = {
            "instId": row['Coin'].replace('-', '').upper(),
            "algoType": "grid",
            "minPx": lower_price,
            "maxPx": upper_price,
            "gridNum": 20,
            "lever": "5",
            "direction": side,
            "investment": "10"
        }
        body = json.dumps(payload)
        print(f"Tạo bot cho {coin}: {side.upper()} tại giá {price} | Vùng {lower_price} - {upper_price}")
        response = requests.post('https://www.okx.com/api/v5/trade/order-algo', headers=headers, data=json.dumps(payload))
        print(response.json())

    except Exception as e:
        print(f"Lỗi khi xử lý {coin}: {e}")
