
import os
import csv
import logging
import requests
from datetime import datetime
import ccxt
import time
import sys
import math
import pandas as pd
# Logging setup

logging.basicConfig(
    level=logging.DEBUG,  # thay vì DEBUG/INFO
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
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
def place_entry_with_tp_sl(exchange, symbol, side, size, entry_price=None, tp_price=None, sl_price=None):
    """
    Đặt lệnh vào futures (market hoặc limit) kèm TP/SL dạng stop-market trên OKX
    """
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

            usdt_limit = 40
            coin_amount = round(usdt_limit /ask_price, 6)
            estimated_value = coin_amount * ask_price

            if estimated_value > usdt_limit:
                coin_amount = round((usdt_limit * 0.999) /ask_price, 6)
                estimated_value  = coin_amount * ask_price

            # ✅ Chuẩn hóa SYMBOL và SIDE từ đầu vào
            symbol_check = symbol.replace("-", "/").upper()
            market = exchange.markets.get(symbol_check)
            symbol_for_order = market['id']
            side_input = side.lower()
            side_check = 'long' if side_input == 'buy' else 'short' if side_input == 'sell' else None
            
            if side_check is None:
                logging.error(f"❌ SIDE không hợp lệ: {side}")
                return
            
            # ✅ Fetch tất cả vị thế hiện tại
            try:
                all_positions = exchange.fetch_positions()
            except Exception as e:
                logging.error(f"❌ Không thể fetch vị thế: {e}")
                return

            has_position_open = False
            for pos in all_positions:
                pos_symbol = pos.get('symbol', '').split(":")[0].upper()        # Ví dụ BTC/USDT:USDT => BTC/USDT
                side_open = pos.get('side') or pos.get('posSide', '')
                side_open = side_open.lower()                         # long / short
                margin_mode = pos.get('marginMode', '')                         # isolated / cross
            
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
            
            # ✅ Duyệt từng dòng trong sheet
            symbol_raw = row[0]                            # Ví dụ: BTC-USDT
            symbol_check = f"{symbol_raw}-SWAP"  # BTC-USDT-SWAP
            symbol_ccxt = f"{symbol_raw.replace("-", "/")}:USDT".upper()   # BTC/USDT:USDT
        
            # ✅ Bước 1: check nếu symbol không nằm trong danh sách fetch từ API OKX
            if symbol_check not in futures_symbols_okx:
                continue
        
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
            # Đặt đòn bẩy 4x
            exchange.set_leverage(4, symbol=symbol_check)
            logging.info(f"⚙️ Đã đặt đòn bẩy 4x cho {symbol}")

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
                        "lever": "4"
                    }
                )
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
                            "lever": "4"
                        }
                    )
                    logging.info(f"✅ [TP/SL] Bắt đầu xử lý cho {symbol} - SIDE: {side}")
                    # ✅ Đợi và retry fetch vị thế sau khi vào lệnh
                    max_retries = 5
                    positions = []
                    for i in range(max_retries):
                        try:
                            positions = exchange.fetch_positions()
                            logging.debug(f"[Retry {i+1}] ✅ Fetch được {len(positions)} vị thế")
                            if positions:
                                break
                        except Exception as e:
                            logging.warning(f"[Retry {i+1}] ❌ Lỗi fetch vị thế: {e}")
                        time.sleep(3)  # chờ rồi thử lại
                except Exception as e2:
                    logging.error(f"❌ Lỗi khi gửi lệnh fallback {symbol} | side={side}: {e2}")
                    continue    
            # ✅ Bắt đầu đặt SL/TP 
            # --- Lấy market price ---
            try:
                ticker = exchange.fetch_ticker(symbol)
                market_price = float(ticker['last'])
                logging.debug(f"✅ [Market Price] Giá thị trường hiện tại của {symbol} = {market_price}")
            except Exception as e:
                logging.error(f"❌ [Market Price] Không lấy được giá hiện tại cho {symbol}: {e}")
                return
                
            # --- Fetch vị thế để lấy size ---
            try:
                positions = exchange.fetch_positions(params={"type": "swap"})
                logging.debug(f"✅ [Positions] Đã fetch vị thế: {positions}")
            except Exception as e:
                logging.error(f"❌ [Positions] Không thể fetch vị thế: {e}")
                return
                
            symbol_check = symbol.replace("-", "/").upper()
            side_check = side.lower()
            size = 0
                
            for pos in positions:
                logging.debug(f"🔍 [Position] Kiểm tra từng vị thế: {pos}")
            
                pos_symbol = pos.get('symbol', '').upper().replace(':USDT', '')
                pos_side = pos.get('posSide', '').lower()  # ✅ Dùng 'posSide' thay vì 'side'
                margin_mode = pos.get('marginMode', '')
                pos_size = pos.get('contracts') or pos.get('size') or pos.get('positionAmt') or pos.get('pos') or pos.get('notionalUsd') or 0
            
                logging.debug(
                    f"🔁 So sánh: pos_symbol={pos_symbol}, pos_side={pos_side}, "
                    f"mode={margin_mode}, size={pos_size} "
                    f"với symbol_check={symbol_check}, side_check={side_check}"
                    f"[DEBUG] size kiểm tra từ pos = {pos_size}"
                )
            
                if (
                    pos_symbol == symbol_check and
                    margin_mode == 'isolated' and
                    float(pos_size) > 0
                ):
                    logging.info(f"✅ [Position] Tìm thấy vị thế hợp lệ để đặt TP/SL cho {symbol_check}")
                    size = float(pos_size)
                    # ✅ Gọi hàm đặt TP/SL kiểu stop-market
                    place_entry_with_tp_sl(
                        exchange=exchange,
                        symbol=symbol,
                        side=side,
                        size=size,
                        entry_price=entry_price,  # hoặc market_price nếu bạn đã lấy
                        tp_price=tp_price,
                        sl_price=sl_price
                    )
                    break
            if size == 0:
                logging.warning(f"⚠️ [Position] Không tìm được vị thế phù hợp để đặt TP/SL cho {symbol}")
                return
                
            # --- Tính toán giá TP / SL ---
            # ✅ Kiểm tra market_price hợp lệ
            if market_price is None or market_price <= 0:
                logging.error(f"❌ Lỗi: market_price không hợp lệ ({market_price}) => Không đặt TP/SL")
                return
            
            if side.lower() == 'buy':
                tp_price = market_price * 1.10
                sl_price = market_price * 0.95
                side_tp_sl = 'sell'
                opposite_side = 'buy' if side.lower() == 'sell' else 'sell'
            else:
                tp_price = market_price * 0.90
                sl_price = market_price * 1.05
                side_tp_sl = 'buy'
                opposite_side = 'buy' if side.lower() == 'sell' else 'sell'
            # ✅ Kiểm tra TP/SL có hợp lệ không
            if tp_price is None or math.isnan(tp_price):
                logging.warning(f"⚠️ TP bị lỗi (None/NaN): tp_price = {tp_price}")
                tp_price = None
            if sl_price is None or math.isnan(sl_price):
                logging.warning(f"⚠️ SL bị lỗi (None/NaN): sl_price = {sl_price}")
                sl_price = None
            
            # Đặt TP (Take Profit)           
            def place_entry_with_tp_sl(exchange, symbol, side, size, entry_price=None, tp_price=None, sl_price=None):
                """
                Đặt lệnh vào futures (market hoặc limit) kèm TP/SL dạng stop-market trên OKX
                """
                try:
                    symbol_okx = symbol.replace("/", "-")
                    order_payload = {
                        'instId': symbol_okx,
                        'tdMode': 'isolated',
                        'side': side.lower(),                    # 'buy' hoặc 'sell'
                        'ordType': 'market' if not entry_price else 'limit',
                        'sz': str(size),
                        'reduceOnly': False
                    }
            
                    # Nếu là lệnh limit thì thêm giá
                    if entry_price:
                        order_payload['px'] = str(round(entry_price, 6))
            
                    # Gắn TP/SL theo dạng trigger (stop-market)
                    attach_algo = []
            
                    # ✅ TP
                    if tp_price and not math.isnan(tp_price):
                        attach_algo.append({
                            'tpTriggerPx': str(round(tp_price, 6)),
                            'tpTriggerPxType': 'last',
                            'tpOrdPx': '-1'   # market
                        })
                    else:
                        logging.warning(f"⚠️ Không có TP hoặc TP invalid cho {symbol}")
            
                    # ✅ SL
                    if sl_price and not math.isnan(sl_price):
                        attach_algo.append({
                            'slTriggerPx': str(round(sl_price, 6)),
                            'slTriggerPxType': 'last',
                            'slOrdPx': '-1'
                        })
                    else:
                        logging.warning(f"⚠️ Không có SL hoặc SL invalid cho {symbol}")
            
                    if attach_algo:
                        order_payload['attachAlgoOrds'] = attach_algo
                        logging.debug(f"[attachAlgoOrds] => {attach_algo}")
            
                    # ✅ Gửi lệnh lên OKX
                    logging.debug(f"[ORDER PAYLOAD] => {order_payload}")
                    response = exchange.private_post_trade_order(order_payload)
                    logging.info(f"✅ Lệnh entry + TP/SL OK: {response}")
            
                except Exception as e:
                    logging.error(f"❌ Lỗi khi đặt entry + TP/SL cho {symbol}: {e}")
        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {e}")
if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")
    run_bot()
