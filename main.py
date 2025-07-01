
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from okx.v5 import Trade as OkxTrade

# ==== 1. ĐỌC SHEET PUBLIC ====
def read_public_google_sheet(sheet_url, sheet_name):
    csv_url = sheet_url.replace("/edit", f"/gviz/tq?tqx=out:csv&sheet={sheet_name}")
    df = pd.read_csv(csv_url)
    df['Thời gian'] = pd.to_datetime(df['Thời gian'], format="%d/%m %H:%M", errors='coerce')
    df.dropna(subset=['Thời gian'], inplace=True)
    return df

# ==== 2. LỌC TÍN HIỆU TRONG 60 PHÚT ====
def get_recent_signals(df):
    now = datetime.now()
    df['Thời gian'] = df['Thời gian'].apply(lambda t: t.replace(year=now.year, month=now.month if t.month == now.month else now.month - 1))
    recent_df = df[df['Thời gian'] >= now - timedelta(minutes=60)]
    return recent_df

# ==== 3. KẾT NỐI OKX ====
def create_okx_client():
    return OkxTrade(
        apiKey=os.getenv("OKX_API_KEY"),
        apiSecretKey=os.getenv("OKX_API_SECRET"),
        passPhrase=os.getenv("OKX_PASSPHRASE"),
        useServerTime=True,
        flag="0"
    )

def get_last_price(instId):
    url = f"https://www.okx.com/api/v5/market/ticker?instId={instId}"
    r = requests.get(url).json()
    return float(r['data'][0]['last'])

# ==== 4. ĐẶT LỆNH ====
def place_order(client, symbol, side, usdt_amount):
    instId = f"{symbol}-USDT-SWAP"
    price = get_last_price(instId)
    qty = round(usdt_amount / price, 3)

    pos_side = "long" if side == "LONG" else "short"
    print(f"→ Gửi lệnh {side} {symbol}, qty {qty}")

    result = client.place_order(
        instId=instId,
        tdMode="cross",
        side="buy" if side == "LONG" else "sell",
        posSide=pos_side,
        ordType="market",
        sz=str(qty)
    )
    print("Đã đặt:", result)

    tp = round(price * 1.1, 2) if side == "LONG" else round(price * 0.9, 2)
    sl = round(price * 0.9, 2) if side == "LONG" else round(price * 1.1, 2)
    print(f"→ Gợi ý TP: {tp}, SL: {sl}")

# ==== 5. CHẠY BOT ====
def run_bot():
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/edit"
    SHEET_NAME = "DATA_12H"
    USDT_PER_TRADE = 10

    df = read_public_google_sheet(SHEET_URL, SHEET_NAME)
    signals = get_recent_signals(df)
    okx_client = create_okx_client()

    for _, row in signals.iterrows():
        symbol = row["Coin"].replace("-USDT", "")
        signal = row["Gợi ý"].strip().upper()
        if signal in ["LONG", "SHORT"]:
            place_order(okx_client, symbol, signal, USDT_PER_TRADE)

if __name__ == "__main__":
    run_bot()
