import os
import json
import pandas as pd
import ccxt
import requests
from datetime import datetime, timedelta

# === Cấu hình ===
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/export?format=csv"
GRID_NUM = 20
LEVERAGE = 5
TRADE_AMOUNT_USDT = 10
PRICE_MARGIN = 0.15  # ±15%
SL_TP_PERCENT = 0.10  # 10%

# === Đọc dữ liệu từ Google Sheet Public ===
def get_sheet_data():
    df = pd.read_csv(SHEET_CSV_URL)
    df.columns = df.columns.str.strip()
    df = df[df["Gợi ý"].isin(["LONG", "SHORT"])]
    return df

# === Kết nối OKX ===
def connect_okx():
    return ccxt.okx({
        'apiKey': os.getenv('OKX_API_KEY'),
        'secret': os.getenv('OKX_API_SECRET'),
        'password': os.getenv('OKX_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
        }
    })

# === Lọc tín hiệu mới trong 60 phút ===
def get_recent_signals(data):
    now = datetime.utcnow() + timedelta(hours=7)
    signals = []

    for _, row in data.iterrows():
        try:
            raw_time = str(row["Thời gian"]).strip()
            dt = datetime.strptime(raw_time, "%d/%m %H:%M").replace(year=now.year)
            if now - dt <= timedelta(minutes=60):
                signals.append(row)
        except Exception as e:
            print(f"Lỗi định dạng thời gian: {e}")

    return signals

# === Đặt Grid lệnh và SL/TP ===
def execute_grid_with_sl_tp(okx, coin, side, markets):
    symbol = f"{coin}-USDT-SWAP"

    if symbol not in markets:
        print(f"❌ Bỏ qua {symbol}: Không có trên OKX Futures")
        return

    try:
        ticker = okx.fetch_ticker(symbol)
        price = ticker['last']
        volume = ticker['quoteVolume']

        if volume < 50000:
            print(f"⚠️ BỎ QUA {symbol}: volume thấp ({volume})")
            return

        # Cài đòn bẩy
        okx.set_leverage(LEVERAGE, symbol=symbol)

        # Tính khoảng giá
        lower = price * (1 - PRICE_MARGIN)
        upper = price * (1 + PRICE_MARGIN)
        step = (upper - lower) / GRID_NUM

        for i in range(GRID_NUM):
            grid_price = lower + i * step
            params = {'reduceOnly': False}
            if side == 'buy':
                okx.create_limit_buy_order(symbol, TRADE_AMOUNT_USDT / grid_price, grid_price, params)
            else:
                okx.create_limit_sell_order(symbol, TRADE_AMOUNT_USDT / grid_price, grid_price, params)

        # Tính SL/TP
        sl_price = price * (1 - SL_TP_PERCENT) if side == 'buy' else price * (1 + SL_TP_PERCENT)
        tp_price = price * (1 + SL_TP_PERCENT) if side == 'buy' else price * (1 - SL_TP_PERCENT)

        print(f"✅ SL tại {sl_price:.4f}, TP tại {tp_price:.4f}")
        # Gợi ý: có thể bổ sung tạo lệnh SL/TP qua conditional order nếu cần

    except Exception as e:
        print(f"❌ LỖI khi đặt lệnh cho {symbol}: {e}")
    # === Chạy chính ===
def main():
    okx = connect_okx()
    data = get_sheet_data()
    signals = get_recent_signals(data)
    markets = okx.load_markets()

    for _, row in pd.DataFrame(signals).iterrows():
        coin = row["coin"].strip()
        suggestion = row["Gợi ý"].strip().lower()
        if suggestion == "long":
            execute_grid_with_sl_tp(okx, coin, "buy", markets)
        elif suggestion == "short":
            execute_grid_with_sl_tp(okx, coin, "sell", markets)

if __name__ == "__main__":
    main()
