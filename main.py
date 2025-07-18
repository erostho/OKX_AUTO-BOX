
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
            max_order_value = 1000000  # giới hạn OKX là 1 triệu
            safe_usdt = min(base_usdt, max_order_value * 0.9)  # chỉ dùng tối đa 90% ngưỡng

            amount = round(safe_usdt / mark_price, 6)
            estimated_value = amount * mark_price

            if estimated_value > max_order_value:
                logging.warning(f"⚠️ Giá trị lệnh ~{estimated_value} USDT vượt giới hạn OKX. Hủy lệnh.")
                return
            logging.info(f"✅ Đặt lệnh {side} {symbol} với amount = {amount}, giá hiện tại = {mark_price}")
            
            # ✅ Kiểm tra vị thế đang mở trước khi đặt lệnh
            logging.info(f"🔍 Kiểm tra vị thế đang mở với symbol = {symbol}, side = {side}")
            
            # Làm sạch symbol để so sánh
            symbol_check = symbol.replace("/", "").replace("-", "").lower()
            
            # Chuẩn hóa side
            side_check = side.lower()
            if side_check in ['s', 'sell']:
                side_check = 'short'
            elif side_check in ['b', 'buy']:
                side_check = 'long'
            
            try:
                all_positions = exchange.fetch_positions()
            except Exception as e:
                logging.error(f"❌ Không thể fetch vị thế: {e}")
                return
            
            logging.debug("---- START Vị thế fetch_positions ----")
            
            for pos in all_positions:
                pos_symbol_raw = pos.get('symbol', '')
                pos_symbol = pos_symbol_raw.replace("/", "").replace("-", "").lower()
                side_open = pos.get('side', '').lower()
                size = float(pos.get('size', 0))
                margin_mode = pos.get('marginMode', '')
            
                logging.debug(
                    f"[DEBUG_POS] raw={pos_symbol_raw} | cleaned={pos_symbol} | "
                    f"side_open={side_open} | size={size} | margin_mode={margin_mode}"
                )
            
                logging.debug(f"[DEBUG_CHECK] So với: symbol_check={symbol_check}, side_check={side_check}")
            
                if (
                    pos_symbol == symbol_check
                    and side_open == side_check
                    and margin_mode == 'isolated'
                    and size > 0
                ):
                    logging.warning(
                        f"⚠️ Đã có vị thế {side_check.upper()} đang mở với {symbol} ({size} hợp đồng). Bỏ qua lệnh."
                    )
                    return
            
            # ✅ Duyệt từng vị thế và kiểm tra trùng khớp
            for pos in all_positions:
                pos_symbol_raw = pos.get('symbol', '')
                pos_symbol = pos_symbol_raw.replace("/", "").replace("-", "").lower()
                margin_mode = pos.get('marginMode', '')
                side_open = pos.get('side', '').lower()
                size = float(pos.get('size', 0))
            
                # ✅ Ghi log từng dòng kiểm tra
                logging.debug(f"[CHECK] ▶ pos_symbol_raw={pos_symbol_raw}, pos_symbol={pos_symbol}, "
                              f"side_open={side_open}, margin_mode={margin_mode}, size={size}")
                
                logging.debug(f"[CHECK] ↪ So với: symbol_check={symbol_check}, side_check={side_check}")
            
                if (
                    pos_symbol == symbol_check and
                    margin_mode == 'isolated' and
                    side_open == side_check and
                    size > 0
                ):
                    logging.warning(f"⚠️ Đã có vị thế {side.upper()} đang mở với {symbol} ({size} hợp đồng, mode={margin_mode}). Bỏ qua lệnh.")
                    return
            
            # 🔁 Lấy giá thị trường hiện tại
            ticker = exchange.fetch_ticker(symbol)
            market_price = ticker['last']

            # ✅ Thiết lập thông số lệnh
            usdt_before_leverage = 20  # mỗi lệnh dùng 20 USDT (trước đòn bẩy)
            leverage = 5
            usdt_total = usdt_before_leverage * leverage  # Tổng giá trị lệnh
            
            # ✅ Tính số lượng coin cần mua
            amount = round(usdt_total / market_price, 6)  # Làm tròn 6 chữ số thập phân
            
            # ✅ Gửi lệnh thị trường
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['ask']
            usdt_amount = 20
            size = round(usdt_amount / price, 6)
            
            order = exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=size,
                params={
                    "tdMode": "isolated",
                    "ccy": "USDT",
                    "reduceOnly": False,
                    "lever": "5"
                }
            )
            except Exception as e:
            logging.error(f"Lỗi xử lý {s}: {e}")
if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")
    run_bot()
