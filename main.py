
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
    format="%(asctime)s - %(levelname)s - %(message)s - datefmt="%H:%M:%S"
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
            def place_tp_sl_order(exchange, symbol, side):
                import logging, time
                logging.info(f"🛠️ Bắt đầu đặt TP/SL cho {symbol} - SIDE: {side}")
                time.sleep(1.5)
            
                try:
                    positions = exchange.fetch_positions([symbol])
                except Exception as ex:
                    logging.error(f"❌ Không thể fetch vị thế: {ex}")
                    return
            
                entry_price, size = 0, 0
                symbol_check = symbol.replace("-", "/").upper()
                side_check = side.lower()
            
                for pos in positions:
                    pos_symbol = pos.get('symbol', '').upper()
                    pos_side = pos.get('side', '').lower()
                    margin_mode = pos.get('marginMode', '')
                    pos_size = pos.get('size') or pos.get('contracts') or pos.get('positionAmt') or 0
                    # ✅ Ưu tiên lấy size đúng format
                    pos_size = float(pos.get('size') or pos.get('positionAmt') or 0)
                    entry_price = float(pos.get('entryPrice') or pos.get('avgPx') or 0)
                
                    # ✅ Log debug tại đây
                    logging.debug(
                        f"[CHECK ENTRY] symbol={pos_symbol}, side={pos_side}, margin_mode={margin_mode}, "
                        f"entry={entry_price}, size={pos_size}"
                    )
                    if (
                        pos_symbol == symbol_check and
                        pos_side == side_check and
                        margin_mode == 'isolated' and
                        float(pos_size) > 0
                    ):
                        entry_price = float(pos.get('entryPrice') or pos.get('avgPx') or 0)
                        size = pos_size
                        logging.info(f"✅ Tìm thấy entry_price = {entry_price}, size = {size}")
                        break
            
                if not entry_price or entry_price == 0:
                    logging.error(f"❌ Không tìm được entry_price hợp lệ để đặt TP/SL cho {symbol}")
                    return
            
                # ✅ Tính TP/SL
                sl_price = entry_price * (0.95 if side == 'buy' else 1.05)
                tp_price = entry_price * (1.10 if side == 'buy' else 0.90)
                side_tp_sl = 'sell' if side == 'buy' else 'buy'
            
                logging.debug(f"📐 TP/SL: TP={tp_price}, SL={sl_price}, side_tp_sl={side_tp_sl}")
            
                # ✅ Gửi lệnh TP
                try:
                    logging.debug(f"📤 Gửi lệnh TP: {symbol}, triggerPx={round(tp_price, 6)}")
                    tp_order = exchange.create_order(
                    time.sleep(1.5)
                    place_tp_sl_order(exchange, symbol, side)
                        symbol=symbol,
                        type='stop-market',
                        side=side_tp_sl,
                        amount=size,
                        params={
                            'triggerPrice': round(tp_price, 6),
                            'triggerType': 'last',
                            'reduceOnly': True
                        }
                    )

                    logging.info(f"✅ Đặt TP thành công: {tp_order}")
                except Exception as ex:
                    logging.error(f"❌ Lỗi đặt TP: {ex}")
                # ✅ Gửi lệnh SL (stop loss)
                try:
                    logging.debug(f"📤 Gửi lệnh SL: {symbol}, triggerPx={round(sl_price,6)}, size={size}")
                    sl_order = exchange.private_post_trade_order_algo({
                        'instId': symbol.replace("/", "-"),
                        'tdMode': 'isolated',
                        'side': side_tp_sl,
                        'ordType': 'trigger',
                        'sz': str(size),
                        'ccy': 'USDT',
                        'triggerPx': str(round(sl_price, 6)),
                        'triggerPxType': 'last',
                        'reduceOnly': True
                    })
                    logging.info(f"✅ Đặt SL thành công: {sl_order}")
                except Exception as ex:
                    logging.error(f"❌ Lỗi đặt lệnh SL: {ex}")
        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {e}")
if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")
    run_bot()

