import os
import ccxt
import gspread
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# Cấu hình
SHEET_URL = 'https://docs.google.com/spreadsheets/d/1AmnD1ekwTZeZrp8kGRCymMDwCySJkec0WdulNX9LyOY/edit'
SHEET_NAME = 'DATA_12H'

GRID_NUM = 20
LEVERAGE = 5
TRADE_AMOUNT_USDT = 10
PRICE_MARGIN = 0.15
SL_TP_PERCENT = 0.10  # 10%

# Kết nối Google Sheet
def get_sheet_data():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)
    return sheet.get_all_records()

# Kết nối OKX
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

# Lọc tín hiệu mới trong 60 phút
def get_recent_signals(data):
    now = datetime.utcnow() + timedelta(hours=7)
    signals = []
    for row in data:
        try:
            raw_time = str(row['Thời gian']).strip()
            dt = datetime.strptime(raw_time, '%d/%m %H:%M').replace(year=now.year)
            if now - dt <= timedelta(minutes=60):
                signals.append(row)
        except Exception as e:
            print(f"Lỗi định dạng thời gian: {e}")
    return signals

# Đặt Grid và SL/TP
def execute_grid_with_sl_tp(okx, coin, side):
    symbol = f"{coin}-USDT-SWAP"
    try:
        ticker = okx.fetch_ticker(symbol)
        price = ticker['last']
        volume = ticker['quoteVolume']

        if volume < 50000:
            print(f"BỎ QUA {symbol}: volume thấp ({volume})")
            return

        okx.set_leverage(LEVERAGE, symbol=symbol)

        min_price = round(price * (1 - PRICE_MARGIN), 4)
        max_price = round(price * (1 + PRICE_MARGIN), 4)
        grid_step = (max_price - min_price) / (GRID_NUM - 1)

        for i in range(GRID_NUM):
            grid_price = round(min_price + i * grid_step, 4)
            qty = round(TRADE_AMOUNT_USDT / grid_price, 4)
            grid_side = side

            okx.create_limit_order(symbol, grid_side, qty, grid_price)
            print(f"Đặt GRID {grid_side.upper()} @ {grid_price} – SL/TP sắp đặt")

            # Đặt SL/TP riêng (stop-market)
            sl_price = round(grid_price * (1 - SL_TP_PERCENT), 4) if side == 'buy' else round(grid_price * (1 + SL_TP_PERCENT), 4)
            tp_price = round(grid_price * (1 + SL_TP_PERCENT), 4) if side == 'buy' else round(grid_price * (1 - SL_TP_PERCENT), 4)

            # Đặt SL
            okx.create_order(symbol, 'stop-market', 'sell' if side == 'buy' else 'buy', qty, None, {
                'triggerPrice': sl_price,
                'stop': 'loss',
                'reduceOnly': True,
            })
            # Đặt TP
            okx.create_order(symbol, 'stop-market', 'sell' if side == 'buy' else 'buy', qty, None, {
                'triggerPrice': tp_price,
                'stop': 'profit',
                'reduceOnly': True,
            })

            print(f"→ SL tại {sl_price}, TP tại {tp_price}")

    except Exception as e:
        print(f"LỖI khi đặt lệnh cho {symbol}: {e}")

def main():
    okx = connect_okx()
    data = get_sheet_data()
    signals = get_recent_signals(data)

    for row in signals:
        coin = row['Coin'].strip()
        suggestion = row['Gợi ý'].strip().lower()
        if suggestion == 'long':
            execute_grid_with_sl_tp(okx, coin, 'buy')
        elif suggestion == 'short':
            execute_grid_with_sl_tp(okx, coin, 'sell')

if __name__ == '__main__':
    main()