
import os
import csv
import logging
import requests
from datetime import timedelta, datetime
import ccxt
import threading
import time
import sys
import json
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

def auto_tp_sl_watcher():
    while True:
        try:
            logging.info("🔁 Đang kiểm tra TP/SL tự động...")
            cancel_tp_sl_if_position_closed(exchange)
            cancel_sibling_algo_if_triggered(exchange)
        except Exception as e:
            logging.error(f"❌ Lỗi trong vòng kiểm tra auto TP/SL: {e}")
        time.sleep(180)
        
def cancel_tp_sl_if_position_closed(exchange):
    try:
        positions = exchange.fetch_positions()
        for pos in positions:
            logging.debug(f"[POSITION] ↪ symbol={pos.get('symbol')} | instId={pos.get('info', {}).get('instId')}")

        for pos in positions:
            size = float(pos.get("size") or 0)
            margin_mode = pos.get("marginMode", "")
            instId = pos.get("info", {}).get("instId", "")

            logging.debug(
                f"[CHECK] ↪ instId={instId} | size={size} | margin={margin_mode}"
            )

            if size == 0 and margin_mode in ["isolated", "cross"]:
                if not instId:
                    logging.warning("⚠️ Thiếu instId, bỏ qua vị thế")
                    continue

                logging.info(f"📉 Đã đóng vị thế {instId} ➝ kiểm tra lệnh TP/SL")

                try:
                    # Fetch all algo orders thuộc instId đó
                    result = exchange.private_get_trade_orders_pending({
                        'instId': instId,
                        'algoType': 'conditional'  # TP/SL trên OKX futures
                    })
                    orders = result.get("data", [])

                    if not orders:
                        logging.info(f"✅ Không còn lệnh TP/SL nào trên {instId}")
                        continue

                    for order in orders:
                        algo_id = order.get("algoId")
                        try:
                            cancel_result = exchange.private_post_trade_cancel_algos({
                                "algos": [algo_id]
                            })
                            logging.info(f"✅ Đã huỷ TP/SL: {algo_id}")
                        except Exception as e:
                            logging.warning(f"❌ Lỗi huỷ TP/SL {algo_id}: {e}")
                            continue

                except Exception as e:
                    logging.error(f"❌ Lỗi kiểm tra TP/SL của {instId}: {e}")
                    continue

    except Exception as e:
        logging.error(f"❌ Lỗi xử lý auto cancel TP/SL: {e}")

def cancel_sibling_algo_if_triggered(exchange):
    try:
        # 🟢 Fetch toàn bộ lệnh TP/SL dạng conditional còn đang treo
        all_algo_orders = exchange.private_get_trade_orders_algo_pending({
            "instType": "SWAP",  # futures perpetual
            "algoType": "conditional"
        }).get("data", [])
        logging.info(f"📋 Đang kiểm tra {len(all_algo_orders)} lệnh TP/SL đang treo...")

        # 🟢 Lấy danh sách instId của các vị thế đang mở
        open_positions = exchange.fetch_positions()
        open_inst_ids = {
            pos.get("info", {}).get("instId", "")
            for pos in open_positions
            if float(pos.get("size", 0)) > 0
        }

        # 🔁 Duyệt từng lệnh đang treo
        for order in all_algo_orders:
            inst_id = order.get("instId", "")
            algo_id = order.get("algoId", "")
            side = order.get("side", "")
            tp_or_sl = order.get("tag", "TP/SL")

            # Nếu không còn vị thế của instId này thì huỷ
            if inst_id not in open_inst_ids:
                logging.info(f"⚠️ instId={inst_id} không còn mở, huỷ lệnh {tp_or_sl} [{side}]...")

                try:
                    response = exchange.private_post_trade_cancel_algos({
                        "algoId": algo_id,
                        "instId": inst_id
                    })
                    logging.info(f"✅ Huỷ thành công lệnh TP/SL: {algo_id} - {inst_id}")
                except Exception as e:
                    logging.error(f"❌ Lỗi huỷ TP/SL {algo_id}: {e}")

    except Exception as e:
        logging.error(f"❌ Lỗi xử lý auto cancel TP/SL: {e}")

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
            created_at = datetime.strptime(created_at_str.strip(), "%Y-%m-%d %H:%M:%S") - timedelta(hours=7)
            elapsed_minutes = (now - created_at).total_seconds() / 60
            if elapsed_minutes > interval:
                logging.info(f"⏱ Lệnh quá hạn: {symbol}")
                continue

            if signal not in ["LONG", "SHORT"]:
                logging.warning("⚠️ Tín hiệu không hợp lệ")
                continue

            side = "buy" if signal == "LONG" else "sell"
            pos_side = "long" if signal == "LONG" else "SHORT"
            
            # Tính khối lượng dựa trên 30 USDT vốn thật và đòn bẩy x5
            usdt_limit = 30
            leverage = 4
            ticker = exchange.fetch_ticker(symbol)
            ask_price = float(ticker.get('ask') or 0)          
            
            if ask_price <= 0:
                logging.error(f"⚠️ Không lấy được giá hợp lệ cho {symbol}")
                continue

            # ✅ Lấy lotSize từ exchange.markets
            symbol_check = symbol.replace("-", "/").upper()
            market = exchange.markets.get(symbol_check)
            lot_size = market['limits']['amount']['min'] or 0.001
            
            # ✅ Tính và làm tròn về đúng bội số
            raw_amount = (usdt_limit * leverage) / ask_price
            coin_amount = round(raw_amount / lot_size) * lot_size
            coin_amount = float(f"{coin_amount:.6f}")  # đảm bảo định dạng

            # ✅ Chuẩn hóa SYMBOL và SIDE từ đầu vào
            symbol_for_order = market['id']
            side_input = side.lower()
            side_check = 'long' if side_input == 'buy' else 'short' if side_input == 'sell' else None
            
            if side_check is None:
                logging.error(f"❌ SIDE không hợp lệ: {side}")
                continue
            
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
            # coin_amount
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
                continue
                
            symbol_check = symbol.replace("-", "/").upper()
            side_input = side.lower()
            side_check = 'long' if side_input == 'buy' else 'short' if side_input == 'sell' else None
            size = 0
            
            # đoạn xử lý SL/TP
            for pos in positions:
                logging.debug(f"[Position] Kiểm tra từng vị thế: {pos}")
            
                pos_symbol = pos.get('symbol', '').upper().replace(':USDT', '')
                pos_side = pos.get('posSide', '').lower()
                margin_mode = pos.get('marginMode', '')
                pos_size = pos.get('contracts') or pos.get('size') or pos.get('positionAmt') or pos.get('pos')
            
                logging.debug(
                    f"🔍 So sánh: pos_symbol={pos_symbol}, pos_side={pos_side}, "
                    f"mode={margin_mode}, size={pos_size} "
                    f"với symbol_check={symbol_check}, side_check={side_check}"
                )
                logging.debug(
                    f"[DEBUG MATCH] So sánh với: symbol_check={symbol_check}, side_check={side_check} "
                    f"vs pos_symbol={pos_symbol}, pos_side={pos_side}, margin_mode={margin_mode}, size={pos_size}"
                )
                if (
                    pos_symbol == symbol_check and
                    pos_side == side_check and
                    margin_mode == 'isolated' and
                    float(pos_size) > 0
                ):
                    logging.info(f"✅ [Position] Tìm thấy vị thế phù hợp để đặt TP/SL cho {symbol_check}")
            
            # 🔄 Chuẩn hóa instId để gọi API Algo
            symbol_instId = f"{symbol_raw.strip().upper()}-SWAP"
            
            # Lấy lot size từ thị trường
            market = exchange.market(symbol_check)
            lot_size = market['limits']['amount']['min'] or 0.001
            
            # Làm tròn size về đúng bội số
            adjusted_size = math.ceil(pos_size / lot_size) * lot_size
            adjusted_size = float(f"{adjusted_size:.6f}")

            # 📈 Tính giá TP/SL
            if side_check == 'long':
                tp_price = market_price * 1.04
                sl_price = market_price * 0.98
                opposite_side = 'sell'
            elif side_check == 'short':
                tp_price = market_price * 0.96
                sl_price = market_price * 1.02
                opposite_side = 'buy'
            else:
                logging.error(f"❌ SIDE không hợp lệ: {side_check}")
                continue
            
            # ✅ Đặt TP
            # Đặt TP
            if tp_price:
                try:
                    tp_order = exchange.private_post_trade_order_algo({
                        "instId": symbol_instId,
                        "tdMode": "isolated",
                        "side": opposite_side,
                        "ordType": "trigger",
                        "triggerPx": str(round(tp_price, 6)),
                        "orderPx": "-1",
                        "triggerPxType": "last",  # BỔ SUNG DÒNG NÀY
                        "sz": str(adjusted_size),
                    })
                    logging.info(f"✅ TP Order Response: {tp_order}")
                except Exception as e:
                    logging.error(f"❌ Lỗi đặt TP: {e}")
                    
            # ✅ Đặt SL
            if tp_price:
                try:
                    tp_order = exchange.private_post_trade_order_algo({
                        "instId": symbol_instId,
                        "tdMode": "isolated",
                        "side": opposite_side,
                        "ordType": "trigger",
                        "triggerPx": str(round(sl_price, 6)),
                        "orderPx": "-1",
                        "triggerPxType": "last",  # BỔ SUNG DÒNG NÀY
                        "sz": str(adjusted_size),
                    })
                    logging.info(f"✅ SL Order Response: {tp_order}")
                except Exception as e:
                    logging.error(f"❌ Lỗi đặt SL: {e}")

            # Gọi hàm huỷ nếu vị thế đã đóng
            # ✅ Chuẩn hoá thành COIN-USDT-SWAP
            symbol_check = symbol_raw.strip().upper().replace("/", "-").replace(":USDT", "-") + "-SWAP"  # FXS-USDT-SWAP
            # ✅ Duyệt vị thế hiện tại
            logging.debug(f"[CHECK] ↪ pos = {pos}")
            def fetch_algo_orders_retry(symbol_instId, retries=5, delay=2):
                for i in range(retries):
                    try:
                        result = exchange.private_get_trade_orders_pending({
                            "instId": symbol_instId,
                            "algoType": "conditional"
                        })
                        data = result.get("data", [])
                        logging.debug(f"[CANCEL TP/SL] ↪ Attempt {i+1}/{retries}, Orders returned: {data}")
                        if data:
                            return data
                        else:
                            time.sleep(delay)
                    except Exception as e:
                        logging.warning(f"[CANCEL TP/SL] ❌ Lỗi khi fetch TP/SL lần {i+1}: {e}")
                        time.sleep(5)
                return []
            try:
                all_positions = exchange.fetch_positions()
                for pos in all_positions:
                    pos_symbol_check = pos.get("symbol", "").upper().replace("/", "-").replace(":USDT", "") + "-SWAP"
                    contracts = float(pos.get("contracts", 0))
                    margin_mode = pos.get("marginMode", "").lower()
                
                    logging.debug(f"[CHECK] ↪ symbol_check={symbol_check}, pos_symbol_check={pos_symbol_check}")
  
                
                    if pos_symbol_check == symbol_check and contracts <= 0.0000001 and margin_mode in ["isolated", "cross"]:
                        logging.warning(f"⚠️ Vị thế {symbol_check} đã đóng → huỷ TP/SL nếu còn treo")
                
                        symbol_instId = pos.get("instId")
                        if not symbol_instId:
                            symbol_instId = symbol_check.replace("/", "-")
                            if not symbol_instId.endswith("-SWAP"):
                                symbol_instId += "-SWAP"
                
                        # fetch TP/SL pending
                        tp_sl_orders = fetch_algo_orders_retry(symbol_instId)
                        ...
                
                        # ✅ Fetch TP/SL đang chờ theo instId
                        def fetch_algo_orders_retry(symbol_instId, retries=5, delay=2):
                            for i in range(retries):
                                try:
                                    res = exchange.private_get_trade_orders_pending({
                                        "instId": symbol_instId,
                                        "algoType": "conditional"
                                    })
                                    data = res.get("data", [])
                                    if data:
                                        return data
                                except Exception as e:
                                    logging.warning(f"❌ Lỗi khi fetch TP/SL lần {i+1}: {e}")
                                time.sleep(delay)
                            return []
                
                        orders_to_cancel = fetch_algo_orders_retry(symbol_instId)
                
                        if not orders_to_cancel:
                            # ✅ Fallback nếu không fetch được theo instId
                            fallback_orders = exchange.private_get_trade_orders_pending({
                                "algoType": "conditional"
                            })
                            all_data = fallback_orders.get("data", [])
                            for o in all_data:
                                if o.get("instId") == symbol_instId and o.get("type") == "stop-market":
                                        orders_to_cancel.append(o)
                
                            # ✅ Huỷ từng lệnh TP/SL
                            for order in orders_to_cancel:
                                algo_id = order.get("algoId")
                                try:
                                    result = exchange.private_post_trade_cancel_algos({
                                        "algos": [algo_id]
                                    })
                                    logging.info(f"✅ Đã huỷ TP/SL: {algo_id}")
                                except Exception as e:
                                    logging.warning(f"❌ Lỗi huỷ TP/SL {algo_id}: {e}")
                        continue  # Qua symbol khác
            except Exception as e:
                logging.error(f"❌ Lỗi kiểm tra vị thế để huỷ TP/SL: {e}")
        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {e}")
if __name__ == "__main__":
    logging.info("🚀 Bắt đầu chạy script main.py")

    # ✅ Khởi động thread trước
    threading.Thread(target=auto_tp_sl_watcher, daemon=True).start()
    logging.info("✅ Đã tạo thread auto_tp_sl_watcher")
    # ✅ Gọi bot xử lý sheet
    run_bot()

    # ✅ Giữ chương trình sống (để thread không bị kill)
    while True:
        time.sleep(60)
