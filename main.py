
import requests
import ccxt
import pandas as pd
import json
import time
import hmac
import base64
import hashlib
from datetime import datetime, timedelta
from pytz import timezone
import os
from pytz import timezone

# Thiết lập thông tin API OKX từ biến môi trường
API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_API_SECRET")
API_PASSPHRASE = os.getenv("OKX_PASSPHRASE")

# Thiết lập đường dẫn sheet CSV công khai
sheet_url = "https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/export?format=csv&gid=1662610713"
df = pd.read_csv(sheet_url)
# =============================================
# ================== Làm sạch và chuẩn hoá cột Thời gian ==================

# Bước 1: loại bỏ dòng null trong cột "Thời gian"
df = df.dropna(subset=["Thời gian"])

# Bước 2: chuyển về chuỗi và làm sạch ký tự ẩn (Unicode space)
df["Thời gian"] = df["Thời gian"].astype(str).str.strip().str.replace(r"\u202f", " ", regex=True)

# Bước 3: cố gắng parse datetime linh hoạt nhất
from dateutil import parser

def try_parse(x):
    try:
        return parser.parse(x, dayfirst=True)
    except:
        return pd.NaT

df["Thời gian"] = df["Thời gian"].apply(try_parse)

# In test
print("🕵️‍♂️ 5 dòng đầu sau khi chuẩn hoá thời gian:", df["Thời gian"].head())
print("❌ Dòng bị lỗi thời gian (NaT):", df["Thời gian"].isna().sum())
print("🟡 Thời gian nhỏ nhất trong sheet:", df["Thời gian"].min())
print("🟢 Thời gian lớn nhất trong sheet:", df["Thời gian"].max())

# ================== Lấy giờ hệ thống UTC+7 ==================

from pytz import timezone
now = datetime.now(timezone("Asia/Ho_Chi_Minh")).replace(tzinfo=None)
print("🕓 Giờ hệ thống (UTC+7):", now)

# ================== Lọc trong 60 phút gần nhất ==================

df = df[df["Thời gian"] > now - timedelta(minutes=60)]
print("✅ Sau khi lọc thời gian 60 phút:", len(df))

# Tiếp tục lọc theo xu hướng nếu muốn
df = df[df["Xu hướng"].str.upper().isin(["TĂNG MẠNH", "GIẢM MẠNH"])]

print("✅ Số coin hợp lệ sau lọc:", len(df))
print(f"Sau khi lọc null: {len(df)}")
print(f"Sau khi lọc xu hướng: {len(df)}")
print(f"Sau khi lọc thời gian 60': {len(df)}")
print(df[["Thời gian"]].head())  # In thử 5 dòng
print("Dòng bị lỗi thời gian (NaT):", df["Thời gian"].isna().sum())
print("Giờ hệ thống (UTC+7):", now)
print("Thời gian nhỏ nhất trong sheet:", df["Thời gian"].min())
print("Thời gian lớn nhất trong sheet:", df["Thời gian"].max())
# Khởi tạo ccxt để lấy giá coin từ OKX
exchange = ccxt.okx()
from datetime import datetime, timedelta
print(f"📊 Số coin hợp lệ sau lọc: {len(df)}")
exchange = ccxt.okx()
markets = exchange.load_markets()

for index, row in df.iterrows():
    try:
        raw_coin = row['Coin'].strip().upper().replace("-", "")
        found_symbol = None

        for sym, market in markets.items():
            if market.get('linear') and market.get('contract') and ':USDT' in sym:
                if raw_coin in sym.replace("/", "").replace(":", ""):
                    found_symbol = sym
                    break

        if not found_symbol:
            print(f"⚠️ Không tìm thấy symbol hợp lệ cho: {raw_coin}")
            continue

        print(f"✅ Symbol OKX hợp lệ: {found_symbol}")
        
        # Lấy giá và thực hiện logic như trước
        ticker = exchange.fetch_ticker(found_symbol)
        price = ticker['last']

        inst_id = found_symbol.replace("/", "-").replace(":", "-").upper()
        if not inst_id.endswith("-SWAP"):
            inst_id += "-SWAP"
        print(f"📦 inst_id dùng để đặt lệnh: {inst_id}")
        side = "long" if row['Xu hướng'].strip().upper() == "TĂNG MẠNH" else "short"

        lower_price = round(price * 0.85, 4)
        upper_price = round(price * 1.15, 4)

        payload = {
            "instId": inst_id,
            "algoType": "grid",
            "minPx": lower_price,
            "maxPx": upper_price,
        }
    # gửi lệnh...
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
        print(f"🔧 Payload: {body}")
        print(f"🔧 Endpoint: https://www.okx.com{request_path}")
        response = requests.post("https://www.okx.com" + request_path, headers=headers, data=body)
        print(response.json())

    except Exception as e:
        print(f"⚠️ Lỗi khi xử lý {row['Coin']}: {e}")
        print(f"⚠️ Lỗi tổng quát: {e}")
        print(f"❌ Lỗi dòng {index + 1}: {e}")
