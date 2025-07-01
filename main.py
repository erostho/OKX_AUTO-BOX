
import requests
import os
import time
import pandas as pd
import json
from datetime import datetime, timedelta

OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_API_SECRET = os.getenv("OKX_API_SECRET")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE")

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/export?format=csv"

HEADERS = {
    "Content-Type": "application/json",
    "OK-ACCESS-KEY": OKX_API_KEY,
    "OK-ACCESS-SIGN": "",
    "OK-ACCESS-TIMESTAMP": "",
    "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE
}

def fetch_sheet_data():
    df = pd.read_csv(SHEET_CSV_URL)
    df.columns = df.columns.str.strip()
    df = df[df["Gợi ý"].isin(["LONG", "SHORT"])]
    return df

def iso_timestamp():
    return datetime.utcnow().isoformat("T", "milliseconds") + "Z"

def sign_request(timestamp, method, request_path, body=""):
    import hmac
    import hashlib
    import base64
    message = f"{timestamp}{method}{request_path}{body}"
    signature = hmac.new(bytes(OKX_API_SECRET, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod=hashlib.sha256).digest()
    return base64.b64encode(signature).decode()

def create_grid_bot(symbol, side, investment_usdt=10, leverage=5, grid_num=20, margin_percent=0.15):
    try:
        price_url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
        r = requests.get(price_url)
        data = r.json()["data"][0]
        last_price = float(data["last"])

        lower_price = round(last_price * (1 - margin_percent), 6)
        upper_price = round(last_price * (1 + margin_percent), 6)

        timestamp = iso_timestamp()
        request_path = "/api/v5/tradingBot/grid/order"
        body_data = {
            "instId": symbol,
            "algoOrdType": "grid",
            "maxPx": str(upper_price),
            "minPx": str(lower_price),
            "gridNum": grid_num,
            "runType": "auto",
            "direction": "short" if side.lower() == "short" else "long",
            "lever": str(leverage),
            "basePos": "false",
            "investment": str(investment_usdt),
            "tradeType": "1"
        }
        body = json.dumps(body_data)
        signature = sign_request(timestamp, "POST", request_path, body)

        headers = HEADERS.copy()
        headers["OK-ACCESS-TIMESTAMP"] = timestamp
        headers["OK-ACCESS-SIGN"] = signature

        url = f"https://www.okx.com{request_path}"
        response = requests.post(url, headers=headers, data=body)
        res_json = response.json()
        if res_json.get("code") == "0":
            print(f"✅ Tạo BOT thành công: {symbol} ({side})")
        else:
            print(f"❌ Lỗi tạo BOT {symbol}: {res_json}")
    except Exception as e:
        print(f"‼️ EXCEPTION {symbol}: {e}")

def main():
    df = fetch_sheet_data()
    now = datetime.now(timezone.utc) + timedelta(hours=7)
    for _, row in df.iterrows():
        try:
            raw_time = str(row["Thời gian"]).strip()
            dt = datetime.strptime(raw_time, "%d/%m %H:%M").replace(year=now.year)

            if now - dt <= timedelta(minutes=60):
                coin = str(row["coin"]).strip().replace("-USDT", "").upper()
                suggestion = str(row["Gợi ý"]).strip().upper()

     # Bỏ qua nếu thiếu dữ liệu hoặc sai format
                if coin == "" or coin == "NAN" or suggestion not in ["LONG", "SHORT"]:
                    print(f"⛔ Bỏ qua dòng lỗi: coin={coin}, suggestion={suggestion}")
                    continue

                inst_id = f"{coin}-USDT-SWAP"
                create_grid_bot(inst_id, suggestion)

        except Exception as e:
            print(f"⚠️ Lỗi đọc dòng: {e}")

if __name__ == "__main__":
    main()
