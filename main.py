
import os
import csv
import logging
from datetime import datetime
import requests
from okx.v5 import Trade, Account

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

api_key = os.getenv("OKX_API_KEY")
api_secret = os.getenv("OKX_API_SECRET")
api_passphrase = os.getenv("OKX_API_PASSPHRASE")
spreadsheet_url = os.getenv("SPREADSHEET_URL")

trade_client = Trade(api_key, api_secret, api_passphrase, flag='1')
account_client = Account(api_key, api_secret, api_passphrase, flag='1')

def fetch_google_sheet_csv(url):
    resp = requests.get(url)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    return list(csv.reader(lines))[1:]  # Bỏ qua header

def run_bot():
    now = datetime.utcnow()
    rows = fetch_google_sheet_csv(spreadsheet_url)
    logging.info(f"📥 Đã tải {len(rows)} tín hiệu từ Google Sheet")

    for row in rows:
        try:
            logging.info(f"🔍 Đang kiểm tra dòng: {row}")
            if len(row) < 7:
                logging.warning(f"⚠️ Bỏ qua dòng không đủ 7 cột: {row}")
                continue

            symbol, signal, entry_price_str, sl_str, tp_str, created_at_str, interval_str = row

            entry_price = float(entry_price_str)
            sl = float(sl_str.strip('%')) / 100
            tp = float(tp_str.strip('%')) / 100
            interval = int(interval_str)

            created_at = datetime.strptime(created_at_str.strip(), "%Y-%m-%d %H:%M:%S")
            elapsed_minutes = (now - created_at).total_seconds() / 60

            if elapsed_minutes > interval:
                logging.info(f"⏩ Bỏ qua lệnh quá hạn {symbol} - {signal}")
                continue

            if signal not in ["LONG", "SHORT"]:
                logging.warning(f"⚠️ Bỏ qua tín hiệu không hợp lệ: {signal}")
                continue

            # Format lại instId chuẩn OKX (ví dụ: BTC-USDT-SWAP)
            inst_id = symbol.replace("USDT", "USDT-SWAP")

            try:
                # Đặt đòn bẩy 5x trước khi đặt lệnh
                account_client.set_leverage(instId=inst_id, lever=5, mgnMode='cross')
                logging.info(f"⚙️ Đã đặt đòn bẩy 5x cho {inst_id}")
            except Exception as e:
                logging.warning(f"⚠️ Không thể đặt đòn bẩy cho {inst_id}: {e}")

            side = "buy" if signal == "LONG" else "sell"
            sz = "20"  # 20 USDT, đã tính toán phù hợp theo margin (hoặc điều chỉnh)

            order_data = {
                "instId": inst_id,
                "tdMode": "cross",
                "side": side,
                "ordType": "market",
                "sz": sz
            }

            logging.info(f"✅ Mở lệnh {signal} {symbol} với {sz} USDT, SL: {sl:.1%}, TP: {tp:.1%}")
            result = trade_client.place_order(**order_data)
            logging.info(f"📦 Kết quả đặt lệnh: {result}")
        except Exception as e:
            logging.error(f"❌ Lỗi xử lý dòng: {row} | Lỗi: {e}")

if __name__ == "__main__":
    run_bot()
