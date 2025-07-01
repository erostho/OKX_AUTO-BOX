
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
import ccxt

# ===== THIẾT LẬP THÔNG SỐ =====
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/gviz/tq?tqx=out:csv&sheet=DATA_12H"
VIETNAM_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
USDT_AMOUNT = 10

# ===== LẤY DỮ LIỆU GOOGLE SHEET =====
def fetch_signals():
    df = pd.read_csv(GOOGLE_SHEET_CSV_URL)
    df.columns = df.columns.str.strip()
    df = df[df["Gợi ý"].isin(["LONG", "SHORT"])]

    now = datetime.now(VIETNAM_TZ)
# Parse cột thời gian
    df["Thời gian"] = pd.to_datetime(df["Thời gian"], format="%d/%m %H:%M")

# Gán năm hiện tại và thêm timezone cho từng dòng
    df["Thời gian"] = df["Thời gian"].apply(lambda x: x.replace(year=now.year).replace(tzinfo=VIETNAM_TZ))

# Lọc các tín hiệu trong vòng 60 phút
    df = df[(now - df["Thời gian"]) <= timedelta(minutes=60)]
    return df

# ===== KẾT NỐI OKX API =====
def connect_okx():
    return ccxt.okx({
        "apiKey": os.getenv("OKX_API_KEY"),
        "secret": os.getenv("OKX_API_SECRET"),
        "password": os.getenv("OKX_PASSPHRASE"),
        "enableRateLimit": True,
        "options": {"defaultType": "spot"}
    })

# ===== TÍNH SL/TP =====
def calculate_sl_tp(side, price):
    sl, tp = None, None
    if side == "buy":
        sl = round(price * 0.90, 4)
        tp = round(price * 1.10, 4)
    else:
        sl = round(price * 1.10, 4)
        tp = round(price * 0.90, 4)
    return sl, tp

# ===== ĐẶT LỆNH GIAO DỊCH =====
def execute_trades(df, okx):
    markets = okx.load_markets()
    for _, row in df.iterrows():
        symbol = row["Coin"].replace("-USDT", "") + "/USDT"
        if symbol not in markets:
            print(f"⛔ Không tìm thấy cặp {symbol}")
            continue

        try:
            ticker = okx.fetch_ticker(symbol)
            price = ticker["last"]
            sl, tp = calculate_sl_tp("buy" if row["Gợi ý"] == "LONG" else "sell", price)
            amount = round(USDT_AMOUNT / price, 6)

            side = "buy" if row["Gợi ý"] == "LONG" else "sell"
            print(f"🚀 Đặt lệnh {side.upper()} {symbol} với giá {price} - SL: {sl}, TP: {tp}")

            order = okx.create_market_order(symbol, side, amount)

            # Đặt TP/SL như lệnh limit riêng (nếu hỗ trợ)
            okx.create_order(symbol, "limit", "sell" if side == "buy" else "buy", amount, tp, {"reduceOnly": True})
            okx.create_order(symbol, "stop_market", "sell" if side == "buy" else "buy", amount, sl, {"reduceOnly": True})
        except Exception as e:
            print(f"❌ Lỗi với {symbol}: {e}")

# ===== MAIN =====
def main():
    print("⚙️ init settings complete")
    df = fetch_signals()
    if df.empty:
        print("📭 Không có tín hiệu mới trong 60 phút")
        return
    okx = connect_okx()
    execute_trades(df, okx)

if __name__ == "__main__":
    main()
