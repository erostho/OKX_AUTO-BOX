
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
            pos_side = "long" if signal == "LONG" else "SHORT"

            # Đặt đòn bẩy 5x
            exchange.set_leverage(5, symbol)
            logging.info(f"⚙️ Đã đặt đòn bẩy 5x cho {symbol}")

            # Tính khối lượng dựa trên 20 USDT vốn thật và đòn bẩy x5
            ticker = exchange.fetch_ticker(symbol)
            mark_price = float(ticker.get('last') or 0)

            if mark_price <= 0:
                logging.error(f"⚠️ Không lấy được giá hợp lệ cho {symbol}")
                return

            base_usdt = 20
            max_order_value = 1000000  # giới hạn OKX
            safe_usdt = min(base_usdt, max_order_value * 0.9)

            amount = round(safe_usdt / mark_price, 6)

            # Nếu số lượng coin vượt ngưỡng cho phép → không đặt
            max_amount_allowed = 999999  # Ngưỡng giới hạn số lượng coin (ví dụ 999,999)
            if amount > max_amount_allowed:
                logging.warning(f"⚠️ Số lượng {amount} quá lớn với giá {mark_price}, bỏ qua lệnh {symbol}")
                return

            # Ước tính lại giá trị để đảm bảo không vượt quá limit OKX
            estimated_value = amount * mark_price
            if estimated_value > max_order_value:
                logging.warning(f"⚠️ Giá trị lệnh ~{estimated_value} USDT vượt giới hạn OKX. Hủy lệnh.")
                return
           
            # Lấy danh sách vị thế
            positions = exchange.fetch_positions()
            # Chuẩn hóa instId
            symbol_swap = symbol + "-SWAP"
            
            # --- KIỂM TRA VỊ THẾ ĐANG MỞ ---
            existing_position = next(
                (p for p in positions if p['symbol'] == symbol and p['info']['posSide'] == pos_side and float(p['info']['availPos']) > 0),
                None
            )
            if existing_position:
                logging.info(f"⚠️ Đã có vị thế {pos_side} đang mở cho {symbol}, bỏ qua không đặt lệnh trùng.")
                return
                
            # Đặt lệnh khi không trùng
            logging.info(f"✅ Đặt lệnh {side} {symbol} với amount = {amount}, giá hiện tại = {mark_price}")
            try:
                order = exchange.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    params={
                        "sz": str(amount),
                        "tdMode": "isolated"
                    }
                )
            except Exception as e:
                logging.error(f"❌ Lỗi khi đặt lệnh: {e}")
            logging.info(f"✅ Mở lệnh {signal} {symbol} với 20 USDT đòn bẩy 5x thành công")
                        # Kiểm tra lệnh có hợp lệ không
            if not order or 'data' not in order or not order['data']:
                logging.error("❌ Không thể lấy order ID vì order không hợp lệ.")
                return
            
            # Lấy order_id để xử lý TP/SL
            order_id = order['data'][0]['ordId']
            
            # Gọi hàm tạo TP/SL
            create_tp_sl_orders(
                exchange=exchange,
                symbol=symbol,
                side=side.upper(),      # "LONG" hoặc "SHORT"
                amount=amount,
                order_id=order_id,
                tp_percent=0.15,        # TP 15%
                sl_percent=0.1         # SL 10%
            )

            def create_tp_sl_orders(exchange, symbol, side, amount, order_id, tp_percent, sl_percent):
            try:
                # Lấy thông tin khớp lệnh
                order_detail = exchange.private_get_trade_order({'ordId': order_id})
                if not order_detail or 'data' not in order_detail or not order_detail['data']:
                    logging.error(f"❌ Không thể lấy thông tin khớp lệnh từ order_id = {order_id}")
                    return


                    avg_price = float(order_detail['data'][0]['avgPx'])
            
                    # Tính giá TP và SL
                    tp_price = avg_price * (1 + tp_percent) if side.upper() == "LONG" else avg_price * (1 - tp_percent)
                    sl_price = avg_price * (1 - sl_percent) if side.upper() == "LONG" else avg_price * (1 + sl_percent)

                    # Gửi lệnh TP
                    exchange.private_post_trade_order_algo({
                        "instId": symbol,
                        "tdMode": "isolated",
                        "side": "sell" if side.upper() == "LONG" else "buy",
                        "ordType": "take_profit",
                        "sz": str(amount),
                        "tpTriggerPx": round(tp_price, 6),
                        "tpOrdPx": "-1"
                    })
            
                    # Gửi lệnh SL
                    exchange.private_post_trade_order_algo({
                        "instId": symbol,
                        "tdMode": "isolated",
                        "side": "sell" if side.upper() == "LONG" else "buy",
                        "ordType": "stop_loss",
                        "sz": str(amount),
                        "slTriggerPx": round(sl_price, 6),
                        "slOrdPx": "-1"
                    })
            
                    logging.info(f"✅ Đã tạo TP/SL cho {symbol} - TP: {tp_price:.6f}, SL: {sl_price:.6f}")
            
                except Exception as e:
                    logging.error(f"❌ Lỗi khi tạo TP/SL: {e}")
            
            
            # --- SAU KHI ĐẶT LỆNH CHÍNH XONG ---
            try:
                order = exchange.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    params={
                        "tdMode": "isolated",
                        "sz": str(amount),
                        "posSide": pos_side
                    }
                 )
            except Exception as e:
                logging.error(f"❌ Lỗi khi đặt lệnh chính: {e}")
                return
        
if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")
    run_bot()
