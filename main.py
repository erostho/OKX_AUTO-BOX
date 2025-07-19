
import os
import csv
import logging
import requests
from datetime import datetime
import ccxt
import time
import pandas as pd
# Logging setup

logging.basicConfig(
    level=logging.DEBUG,  # thay vì DEBUG/INFO
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


            # Tính khối lượng dựa trên 20 USDT vốn thật và đòn bẩy x5
            ticker = exchange.fetch_ticker(symbol)
            ask_price = float(ticker.get('ask') or 0)          
            
            if ask_price <= 0:
                logging.error(f"⚠️ Không lấy được giá hợp lệ cho {symbol}")
                return

            usdt_limit = 50
            coin_amount = round(usdt_limit /ask_price, 6)
            estimated_value = coin_amount * ask_price

            if estimated_value > usdt_limit:
                coin_amount = round((usdt_limit * 0.999) /ask_price, 6)
                estimated_value  = coin_amount * ask_price
            logging.info(
                f"✅ Đặt lệnh {side.upper()} {symbol} với {coin_amount} coin (~{estimated_value:.2f} USDT), "
                f"giá ask = {ask_price}"
            ) 
            # ✅ Chuẩn hóa SYMBOL và SIDE từ đầu vào
            symbol_check = symbol.replace("-", "/").upper()
            market = exchange.markets.get(symbol_check)
            symbol_for_order = market['id']
            side_input = side.lower()
            side_check = 'long' if side_input == 'buy' else 'short' if side_input == 'sell' else None
            
            if side_check is None:
                logging.error(f"❌ SIDE không hợp lệ: {side}")
                return
            
            logging.info(f"🔍 Kiểm tra vị thế đã mở với SYMBOL = {symbol_check}, SIDE = {side_check}")
            
            # ✅ Fetch tất cả vị thế hiện tại
            try:
                all_positions = exchange.fetch_positions()
            except Exception as e:
                logging.error(f"❌ Không thể fetch vị thế: {e}")
                return
            
            logging.debug("--- START kiểm tra vị thế từ OKX ---")
            has_position_open = False
            for pos in all_positions:
                pos_symbol = pos.get('symbol', '').split(":")[0].upper()        # Ví dụ BTC/USDT:USDT => BTC/USDT
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
                    logging.warning(f"⚠️ ĐÃ CÓ VỊ THẾ {side_check.upper()} mở với {symbol_check} => KHÔNG đặt thêm lệnh")
                    has_position_open = True
                    break # không cần kiểm tra thêm
            # ✅ Đã có vị thế bỏ qua coin này
            if has_position_open:
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
            
            # ✅ Lấy danh sách symbols từ API OKX (Futures)
            futures_symbols_okx = fetch_okx_usdt_futures_symbols()
            logging.info(f"✅ Đã load {len(futures_symbols_okx)} USDT-M Futures symbols từ OKX")
            
            # ✅ Duyệt từng dòng trong sheet
            symbol_raw = row[0]                            # Ví dụ: BTC-USDT
            symbol_check = f"{symbol_raw}-SWAP"  # BTC-USDT-SWAP
            symbol_ccxt = f"{symbol_raw.replace("-", "/")}:USDT".upper()   # BTC/USDT:USDT
        
            # ✅ Bước 1: check nếu symbol không nằm trong danh sách fetch từ API OKX
            if symbol_check not in futures_symbols_okx:
                logging.warning(f"⚠️ Symbol {symbol_check} KHÔNG nằm trong danh sách USDT-M Futures. Bỏ qua.")
                continue
        
            logging.info(f"✅ Symbol {symbol_check} HỢP LỆ. Tiếp tục xử lý...")
        
            # ✅ Bước 2: Check trong exchange.markets xem symbol có tồn tại và đúng loại không
            market = exchange.markets.get(symbol_ccxt)
        
            if not market:
                logging.error(f"❌ Symbol {symbol_ccxt} không tồn tại trong exchange.markets!")
                continue
        
            # ✅ Bước 3: Check đúng loại USDT-M Futures/Swap (Linear)
            market_type = market.get('type')
            settle_coin = market.get('settle')
                        
            if settle_coin and settle_coin.lower() == 'usdt' and market_type in ['future', 'swap']:
                logging.info(f"✅ Symbol {symbol_ccxt} là USDT-M {market_type.upper()} ➜ Cho phép đặt lệnh")
            else:
                logging.error(f"❌ Symbol {symbol_ccxt} không phải USDT-M Futures (type={market_type}, settle={settle_coin})! Bỏ qua...")
                continue
       
            # ✅ vào lệnh
            # Đặt đòn bẩy 5x
            exchange.set_leverage(5, symbol=symbol_check)
            logging.info(f"⚙️ Đã đặt đòn bẩy 5x cho {symbol}")

            symbol_for_order = market['id']
            # ✅ Vào lệnh — ưu tiên dùng symbol_for_order
            try:
                order = exchange.create_market_order(
                    symbol=symbol_for_order,
                    side=side,
                    amount=coin_amount,
                    params={
                        "tdMode": "isolated",
                        "ccy": "USDT",
                        "reduceOnly": False,
                        "lever": "5"
                    }
                )
                logging.info(f"📌 SYMBOL ĐẶT LỆNH (OKX ID): {symbol_for_order}")
                logging.info(f"📥 Kết quả tạo lệnh: {order}")
            except Exception as e:
                logging.warning(f"⚠️ Lỗi với symbol_for_order. Thử lại với symbol: {e}")
                try:
                    order = exchange.create_market_order(
                        symbol=symbol,
                        side=side,
                        amount=coin_amount,
                        params={
                            "tdMode": "isolated",
                            "ccy": "USDT",
                            "reduceOnly": False,
                            "lever": "5"
                        }
                    )
                    logging.info(f"📌 SYMBOL ĐẶT LỆNH (symbol): {symbol}")
                    logging.info(f"📥 Kết quả tạo lệnh fallback: {order}")
                except Exception as e2:
                    logging.error(f"❌ Lỗi khi gửi lệnh fallback {symbol} | side={side}: {e2}")
                    continue
           
            # ✅ Kiểm tra phản hồi hợp lệ từ lệnh để SL/TP            
           
            def place_tp_sl_order(exchange, symbol, side, entry_price):
                logging.info(f"🟡 Bắt đầu đặt TP/SL cho {symbol} - SIDE: {side}, ENTRY: {entry_price}")
            
                # ✅ Tính giá TP/SL
                sl_price = entry_price * (0.95 if side == 'buy' else 1.05)
                tp_price = entry_price * (1.10 if side == 'buy' else 0.90)
                side_tp_sl = 'sell' if side == 'buy' else 'buy'
            
                logging.debug(f"✅ TP/SL: TP={tp_price}, SL={sl_price}, side_tp_sl={side_tp_sl}")
            
                # ✅ Chờ 1 giây để dữ liệu vị thế ổn định
                time.sleep(1)
            
                try:
                    positions = exchange.fetch_positions([symbol])
                except Exception as e:
                    logging.error(f"❌ Lỗi khi fetch vị thế: {e}")
                    return
            
                # ✅ Chuẩn hóa symbol và side
                symbol_check = symbol.replace("-", "/").upper()
                side_check = 'long' if side == 'buy' else 'short'
                amount = 0
            
                for pos in positions:
                    pos_symbol = pos.get('symbol', '').upper()
                    pos_side = pos.get('side', '').lower()
                    margin_mode = pos.get('marginMode', '')
                    size_raw = pos.get('size', None)
            
                    logging.debug(f"[CHECK SIZE] pos_symbol={pos_symbol}, pos_side={pos_side}, margin={margin_mode}, size_raw={size_raw}")
            
                    if pos_symbol == symbol_check and pos_side == side_check and margin_mode == 'isolated':
                        amount = float(size_raw) if size_raw not in [None, "None", ""] else 0
                        break
            
                logging.debug(f"[CHECK SIZE FINAL] symbol={symbol}, amount={amount}")
                if amount == 0:
                    logging.warning(f"⚠️ Không tìm thấy size phù hợp để đặt TP/SL cho {symbol}")
                    return
            
                # ✅ Đặt Take Profit
                try:
                    tp_order = exchange.create_order(
                        symbol=symbol,
                        type='trigger',
                        side=side_tp_sl,
                        amount=amount,
                        params={
                            "triggerPrice": round(tp_price, 4),
                            "orderPx": round(tp_price, 4),
                            "triggerType": "mark",
                            "marginMode": "isolated"
                        }
                    )
                    logging.info(f"✅ Đã đặt TP cho {symbol}: {tp_order}")
                except Exception as e:
                    logging.error(f"❌ Lỗi khi đặt TP cho {symbol}: {e}")
            
                # ✅ Đặt Stop Loss
                try:
                    sl_order = exchange.create_order(
                        symbol=symbol,
                        type='trigger',
                        side=side_tp_sl,
                        amount=amount,
                        params={
                            "triggerPrice": round(sl_price, 4),
                            "orderPx": round(sl_price, 4),
                            "triggerType": "mark",
                            "marginMode": "isolated"
                        }
                    )
                    logging.info(f"✅ Đã đặt SL cho {symbol}: {sl_order}")
                except Exception as e:
                    logging.error(f"❌ Lỗi khi đặt SL cho {symbol}: {e}")
                    
            # 🟦 Tính entry_price và đặt TP/SL
            entry_price = float(pos.get('entryPrice') or pos.get('avgPx') or 0)
            logging.info(f"📌 Entry từ order['info']: {entry_price}")
            
            # ⛳ Nếu vẫn không có entry_price thì check lại từ vị thế
            if entry_price == 0:
                try:
                    symbol_check = symbol.replace("-", "/").upper()
                    side_check = side.lower()
                    logging.info(f"🔍 Đang kiểm tra lại entry_price từ vị thế: symbol_check={symbol_check}, side_check={side_check}")
            
                    positions = exchange.fetch_positions([symbol])
                    for pos in positions:
                        logging.info(f"↪️ pos_symbol={pos['symbol']} | pos_side={pos['side']} | entryPrice={pos.get('entryPrice')}")
                        if pos['symbol'].upper() == symbol_check and pos['side'].lower() == side_check:
                            entry_price = float(pos.get('entryPrice') or pos.get('avgPx') or 0)
                            logging.info(f"✅ Tìm thấy entry_price từ vị thế: {entry_price}")
                            break
                except Exception as ex:
                    logging.error(f"❌ Không thể fetch vị thế để lấy entry_price: {ex}")
            
            # ⛳ Nếu có entry_price thì đặt TP/SL
            if entry_price > 0:
                place_tp_sl_order(exchange, symbol, side, entry_price)
            else:
                logging.warning(f"⚠️ Không xác định được entry_price để đặt TP/SL cho {symbol} | side={side} | symbol_check={symbol_check}")

        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {e}")
if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")
    run_bot()
