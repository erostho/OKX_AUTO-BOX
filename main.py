import requests
import ccxt
import pandas as pd
from datetime import datetime, timedelta

# Thiết lập thông tin API OKX
API_KEY = 'YOUR_API_KEY'
API_SECRET = 'YOUR_API_SECRET'
API_PASSPHRASE = 'YOUR_API_PASSPHRASE'

# Thiết lập headers cho API OKX
headers = {
    'Content-Type': 'application/json',
    'OK-ACCESS-KEY': API_KEY,
    'OK-ACCESS-SIGN': '',  # Sẽ được tính bằng HMAC SHA256
    'OK-ACCESS-TIMESTAMP': '',
    'OK-ACCESS-PASSPHRASE': API_PASSPHRASE,
}

# Đọc dữ liệu từ Google Sheet public CSV
sheet_url = 'https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/gviz/tq?tqx=out:csv&sheet=DATA_12H'
df = pd.read_csv(sheet_url)

# Chuẩn hoá dữ liệu và lọc theo điều kiện
df = df.dropna()
df['Thời gian'] = pd.to_datetime(df['Thời gian'], format='%d/%m/%Y %H:%M:%S')
now = datetime.now()
df = df[df['Thời gian'] > now - timedelta(minutes=60)]
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

        print(f"Tạo bot cho {coin}: {side.upper()} tại giá {price} | Vùng {lower_price} - {upper_price}")
        # response = requests.post('https://www.okx.com/api/v5/trade/order-algo', headers=headers, data=json.dumps(payload))
        # print(response.json())

    except Exception as e:
        print(f"Lỗi khi xử lý {coin}: {e}")
