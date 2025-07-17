import os
import requests
import pandas as pd
from datetime import datetime, timedelta
import ccxt
import time

# Lấy API từ biến môi trường
api_key = os.getenv("OKX_API_KEY")
api_secret = os.getenv("OKX_API_SECRET")
api_passphrase = os.getenv("OKX_PASSPHRASE")
spreadsheet_url = os.getenv("SPREADSHEET_URL")

# Thiết lập OKX
exchange = ccxt.okx({
    'apiKey': api_key,
    'secret': api_secret,
    'password': api_passphrase,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap'
    }
})

def fetch_signal_data():
    df = pd.read_csv(spreadsheet_url)
    df = df[df['Tín hiệu'].isin(['LONG', 'SHORT'])]

    now = datetime.utcnow()
    df['Thời gian'] = pd.to_datetime(df['Thời gian'], errors='coerce')
    df = df[df['Thời gian'].notna()]
    df = df[df['Thời gian'] > now - timedelta(minutes=60)]
    return df

def place_order(symbol, signal):
    try:
        market = exchange.market(symbol)
        price = exchange.fetch_ticker(symbol)['last']
        usdt_amount = 20
        leverage = 5
        quantity = round(usdt_amount / price * leverage, 4)

        print(f"--- Đang đặt lệnh {signal} cho {symbol} ---")
        print(f"📉 Giá hiện tại: {price}")
        print(f"🎯 Số lượng đặt: {quantity}")

        exchange.set_leverage(leverage, symbol)

        side = 'buy' if signal == 'LONG' else 'sell'
        order = exchange.create_market_order(symbol, 'swap', side, quantity, {
            'tdMode': 'isolated'
        })

        print(f"✅ Đặt lệnh {side} thành công: {order['id']}")

        # Tính TP và SL
        tp_price = round(price * 1.2, 4) if side == 'buy' else round(price * 0.8, 4)
        sl_price = round(price * 0.9, 4) if side == 'buy' else round(price * 1.1, 4)

        # Đặt TP
        tp = exchange.create_order(symbol, 'take_profit_market', 'sell' if side == 'buy' else 'buy',
                                   quantity, None, {
            'tdMode': 'isolated',
            'tpTriggerPx': tp_price,
            'tpOrdPx': -1,
            'reduceOnly': True
        })

        # Đặt SL
        sl = exchange.create_order(symbol, 'stop_market', 'sell' if side == 'buy' else 'buy',
                                   quantity, None, {
            'tdMode': 'isolated',
            'slTriggerPx': sl_price,
            'slOrdPx': -1,
            'reduceOnly': True
        })

        print(f"🎯 Đã đặt TP tại: {tp_price}, SL tại: {sl_price}")
    except Exception as e:
        print(f"❌ Lỗi đặt lệnh {symbol}: {str(e)}")

def main():
    try:
        df = fetch_signal_data()
        if df.empty:
            print("⚠️ Không có tín hiệu mới trong 60 phút.")
            return

        print(f"📊 Số tín hiệu hợp lệ: {len(df)}")
        for _, row in df.iterrows():
            coin = row['Coin']
            signal = row['Tín hiệu']
            symbol = f"{coin.upper()}/USDT:USDT"
            print(f"📦 Xử lý coin: {symbol} với tín hiệu: {signal}")
            place_order(symbol, signal)
            time.sleep(1)
    except Exception as e:
        print(f"‼️ Lỗi tổng: {str(e)}")

if __name__ == "__main__":
    main()
