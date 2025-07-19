
import os
import csv
import logging
import requests
from datetime import datetime
import ccxt
import pandas as pd
# Logging setup

logging.basicConfig(
    level=logging.INFO,  # thay vì DEBUG/INFO
    format="%(asctime)s - %(levelname)s - %(message)s"
)
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
            
            # ✅ Lấy danh sách symbols từ API OKX (Futures)
            futures_symbols_okx = fetch_okx_usdt_futures_symbols()
            logging.info(f"✅ Đã load {len(futures_symbols_okx)} USDT-M Futures symbols từ OKX")
            
            # ✅ Duyệt từng dòng trong sheet
            symbol_raw = row[0]                            # Ví dụ: BTC-USDT
            symbol_check = f"{symbol_raw}-SWAP"  # BTC-USDT-SWAP
            symbol_ccxt = f"{symbol_raw.replace("-", "/")}:USDT".upper()   # BTC/USDT:USDT
            
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
            
            # ✅ Chuẩn hóa SYMBOL và SIDE từ đầu vào
            symbol_check = symbol.replace("-", "/").upper()
            side_input = side.lower()
            side_check = 'long' if side_input == 'buy' else 'short' if side_input == 'sell' else None
            
            if side_check is None:
                logging.error(f"❌ SIDE không hợp lệ: {side}")
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
            
            logging.info(f"🔍 Kiểm tra vị thế đã mở với SYMBOL = {symbol_check}, SIDE = {side_check}")
            
            # ✅ Fetch tất cả vị thế hiện tại
            try:
                all_positions = exchange.fetch_positions()
            except Exception as e:
                logging.error(f"❌ Không thể fetch vị thế: {e}")
                return
                            logging.debug("--- START kiểm tra vị thế từ OKX ---")
                for pos in all_positions:
                    pos_symbol = pos.get('symbol', '').upper()                      # Ví dụ BTC/USDT
                    side_open = pos.get('side', '').lower()                         # long / short
                    margin_mode = pos.get('marginMode', '')                         # isolated / cross
                
                    logging.debug(
                        f"[CHECK] ↪ pos_symbol={pos_symbol}, side_open={side_open}, "
                        f"margin_mode={margin_mode}"
                    )
                    logging.debug(
                        f"[CHECK] ↪ So với: symbol_check={symbol_check}, side_check={side_check}"
                    )
                
                    if (
                        pos_symbol == symbol_check and
                        side_open == side_check and
                        margin_mode == 'isolated'
                    ):
                        logging.warning(
                            f"⚠️ ĐÃ CÓ VỊ THẾ {side_check.upper()} mở với {symbol_check} => KHÔNG đặt thêm lệnh"
                        )
                        continue        
            # ⚙️ Cấu hình load markets cho futures
            exchange.options['defaultType'] = 'future'
            exchange.load_markets()
            market = exchange.markets.get(symbol_check)

            # ✅ Hàm lấy danh sách symbol USDT-M Futures trực tiếp từ OKX
            def fetch_okx_usdt_futures_symbols():
                url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"  # hoặc FUTURES nếu bạn muốn FUTURES thay vì perpetual
                try:
                    response = requests.get(url)
                    response.raise_for_status()
                    data = response.json()
                    instruments = data.get("data", [])
                    symbols = []
            
                    for item in instruments:
                        # Chỉ chọn USDT-M (linear), bỏ qua COIN-M
                        if item.get("settleCcy") == "USDT" and item.get("ctType") in ["linear", None]:
                            inst_id = item["instId"]  # VD: BTC-USDT-SWAP
                            symbols.append(inst_id)
            
                    return list(set(symbols))  # Loại trùng
                except Exception as e:
                    logging.error(f"❌ Không thể fetch Futures symbols từ OKX: {e}")
                    return []
                    
            # ✅ Bước 1: check nếu symbol không nằm trong danh sách fetch từ API OKX
            if symbol_check not in futures_symbols_okx:
                logging.warning(f"⚠️ Symbol {symbol_check} KHÔNG nằm trong danh sách USDT-M Futures. Bỏ qua.")
                continue
            
            logging.info(f"✅ Symbol {symbol_check} HỢP LỆ. Tiếp tục xử lý...")
            
            # ✅ Bước 2: Check trong exchange.markets xem symbol có tồn tại và đúng loại không
            market = exchange.markets.get(symbol_ccxt)
            logging.debug(f"↪ Thông tin thị trường: {market}")
            
            if not market:
                logging.error(f"❌ Symbol {symbol_ccxt} không tồn tại trong exchange.markets!")
                continue
            
            # ✅ Bước 3: Check đúng loại USDT-M Futures/Swap (Linear)
            market_type = market.get('type')
            settle_coin = market.get('settle')
                
            logging.debug(f"↪ Kiểm tra type={market_type}, settle={settle_coin}")
                
            if settle_coin and settle_coin.lower() == 'usdt' and market_type in ['future', 'swap']:
                logging.info(f"✅ Symbol {symbol_ccxt} là USDT-M {market_type.upper()} ➜ Cho phép đặt lệnh")
                continue
            logging.error(f"❌ Symbol {symbol_ccxt} không phải USDT-M Futures (type={market_type}, settle={settle_coin})! Bỏ qua...")
            continue
            
            
            # ✅ vào lệnh 
            logging.info(f"🔄 Gửi lệnh market: symbol={symbol}, side={side}, size={size}, params={params}")
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
            # ✅ Kiểm tra phản hồi hợp lệ từ lệnh
            if (
                not order
                or 'data' not in order
                or not isinstance(order['data'], list)
                or len(order['data']) == 0
                or 'ordId' not in order['data'][0]
            ):
                logging.error(f"❌ Lệnh không hợp lệ, không tạo TP/SL. Phản hồi: {order}")
                continue

            order_id = order['data'][0]['ordId']
            logging.info(f"⚠️ Order ID: {order_id}")
            logging.info(f"✅ Mở lệnh {signal} {symbol} với 20 USDT đòn bẩy 5x thành công")
            
            # ✅ Gọi API để lấy thông tin order đã khớp, bao gồm giá khớp (avgPx)
            order_detail = exchange.private_get_trade_order({'ordId': order_id})

            # ✅ Kiểm tra dữ liệu trả về từ API
            if not order_detail or 'data' not in order_detail or not order_detail['data']:
                logging.error(f"❌ Không thể lấy thông tin khớp lệnh từ order_id = {order_id}")
                continue

            # ✅ Nếu dữ liệu hợp lệ, lấy giá trung bình khớp lệnh
            avg_price = float(order_detail['data'][0].get('avgPx', 0))

            # ✅ Nếu avg_price = 0 thì không nên tiếp tục
            if avg_price == 0:
                logging.error(f"❌ Giá avgPx = 0 từ order_id = {order_id}, không tạo được TP/SL")
                continue
                
            # ✅ Tính TP và SL theo % nhập từ Google Sheet
            tp_price = avg_price * (1 + tp) if signal == "LONG" else avg_price * (1 - tp)
            sl_price = avg_price * (1 - sl) if signal == "LONG" else avg_price * (1 + sl)

            # ✅ Tạo TP (Take Profit)
            exchange.private_post_trade_order_algo({
                "instId": symbol,
                "tdMode": "isolated",
                "side": "sell" if signal == "LONG" else "buy",
                "ordType": "take_profit",
                "sz": str(amount),
                "tpTriggerPx": round(tp_price, 6),
                "tpOrdPx": "-1"
            })

            # ✅ Tạo SL (Stop Loss)
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
