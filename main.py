
import os
import csv
import logging
import requests
from datetime import datetime
import ccxt

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# Đọc biến môi trường
SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")
OKX_API_KEY = os.environ.get("OKX_API_KEY")
OKX_API_SECRET = os.environ.get("OKX_API_SECRET")
OKX_API_PASSPHRASE = os.environ.get("OKX_API_PASSPHRASE")

# Khởi tạo OKX
exchange = ccxt.okx({
    'apiKey': OKX_API_KEY,
    'secret': OKX_API_SECRET,
    'password': OKX_API_PASSPHRASE,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap'
    }
})

def fetch_sheet():
    try:
        csv_url = SPREADSHEET_URL.replace("/edit#gid=", "/export?format=csv&gid=")
        res = requests.get(csv_url)
        res.raise_for_status()
        return list(csv.reader(res.content.decode("utf-8").splitlines()))
    except Exception as e:
        logging.error(f"❌ Không thể tải Google Sheet: {e}")
        return []

def run_bot():
    now = datetime.utcnow()
    rows = fetch_sheet()
    if not rows:
        return
    rows = rows[1:]

    for row in rows:
        try:
            logging.info(f"🔍 Kiểm tra dòng: {row}")
            if len(row) < 7:
                logging.warning("⚠️ Dòng thiếu dữ liệu")
                continue

            symbol, signal, entry_price, sl_str, tp_str, created_at_str, interval = row
            entry_price = float(entry_price)
            sl = float(sl_str.strip('%')) / 100
            tp = float(tp_str.strip('%')) / 100
            interval = int(interval)
            created_at = datetime.strptime(created_at_str.strip(), "%Y-%m-%d %H:%M:%S")

            elapsed_minutes = (now - created_at).total_seconds() / 60
            if elapsed_minutes > interval:
                logging.info(f"⏱ Lệnh quá hạn: {symbol}")
                continue

            if signal not in ["LONG", "SHORT"]:
                logging.warning("⚠️ Tín hiệu không hợp lệ")
                continue

            side = "buy" if signal == "LONG" else "sell"
            pos_side = "long" if signal == "LONG" else "short"

            # Đặt đòn bẩy 5x
            exchange.set_leverage(5, symbol)
            logging.info(f"⚙️ Đã đặt đòn bẩy 5x cho {symbol}")

            # Tính khối lượng dựa trên 20 USDT vốn thật và đòn bẩy x5
            market = exchange.market(symbol)
            ticker = exchange.fetch_ticker(symbol)
            mark_price = float(ticker['last']) if ticker['last'] else 0

            if mark_price <= 0:
                logging.error(f"⚠️ Không lấy được giá hợp lệ cho {symbol}")
                return

            amount = 20

            if amount <= 0:
                logging.error("⚠️ Không thể tính được số lượng hợp lệ để đặt lệnh")
                return

            logging.info(f"✅ Đặt lệnh {side} {symbol} với amount = {amount}, giá hiện tại = {mark_price}")

            order = exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=20,
                params={
                    "sz": str(amount),
                    "tdMode": "isolated",
                }
            )
            logging.info(f"✅ Mở lệnh {signal} {symbol} với 20 USDT đòn bẩy 5x thành công")
            
            # Lấy order ID sau khi đặt lệnh chính
            order_id = order['data'][0]['ordId']

            # Gọi API để lấy thông tin order đã khớp, bao gồm giá khớp (avgPx)
            order_detail = exchange.private_get_trade_order({'ordId': order_id})
            avg_price = float(order_detail['data'][0]['avgPx'])

            # Tính TP và SL theo % nhập từ Google Sheet
            tp_price = avg_price * (1 + tp) if signal == "LONG" else avg_price * (1 - tp)
            sl_price = avg_price * (1 - sl) if signal == "LONG" else avg_price * (1 + sl)

            # Tạo TP (Take Profit)
            exchange.private_post_trade_order_algo({
                "instId": symbol,
                "tdMode": "isolated",
                "side": "sell" if signal == "LONG" else "buy",
                "ordType": "take_profit",
                "sz": str(amount),
                "tpTriggerPx": round(tp_price, 6),
                "tpOrdPx": "-1"
            })

            # Tạo SL (Stop Loss)
            exchange.private_post_trade_order_algo({
                "instId": symbol,
                "tdMode": "isolated",
                "side": "sell" if signal == "LONG" else "buy",
                "ordType": "stop_loss",
                "sz": str(amount),
                "slTriggerPx": round(sl_price, 6),
                "slOrdPx": "-1"
            })
            exchange.private_post_trade_order_algo({
                "instId": symbol,
                "tdMode": "isolated",
                "side": "sell" if signal == "LONG" else "buy",
                "ordType": "take_profit",
                "sz": str(amount),
                "tpTriggerPx": round(tp_price, 6),
                "tpOrdPx": "-1",
            })

            exchange.private_post_trade_order_algo({
                "instId": symbol,
                "tdMode": "isolated",
                "side": "sell" if signal == "LONG" else "buy",
                "ordType": "stop",
                "sz": str(amount),
                "slTriggerPx": round(sl_price, 6),
                "slOrdPx": "-1",
                "posSide": pos_side
            })

            logging.info(f"🎯 TP/SL đặt xong cho {symbol}: TP={round(tp_price,6)} | SL={round(sl_price,6)}")

        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {e}")

if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")
    run_bot()
