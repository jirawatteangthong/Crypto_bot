import ccxt
import time
import requests
from datetime import datetime, timedelta

# --- ตั้งค่า ---
api_key = '8f528085-448c-4480-a2b0-d7f72afb38ad'
secret = '05A665CEAF8B2161483DF63CB10085D2'
password = 'Jirawat1-'

symbol = 'BTC/USDT:USDT'
position_size = 0.7
cooldown_after_sl_minutes = 5

telegram_token = '7752789264:AAF-0zdgHsSSYe7PS17ePYThOFP3k7AjxBY'
telegram_chat_id = '# --- Telegram แจ้งเตือน ---

def telegram(message):
    requests.get(f'https://api.telegram.org/bot{telegram_token}/sendMessage',
                 params={'chat_id': telegram_chat_id, 'text': 

# --- OKX setup ---
exchange = ccxt.okx({
    'apiKey': api_key,
    'secret': secret,
    'password': password,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})
exchange.set_sandbox_mode(False)  # เปลี่ยนเป็น True ถ้าจะทดสอบใน Sandbox

last_sl_time = None

# --- ราคา + กราฟ ---
def fetch_price():
    return float(exchange.fetch_ticker(symbol)['last'])

def fetch_candles():
    return exchange.fetch_ohlcv(symbol, timeframe='5m', limit=3)

# --- ตรวจแท่งกลับตัว ---
def is_bullish_engulfing(candles):
    c1, c2 = candles[-2], candles[-1]
    return c1[1] > c1[4] and c2[4] > c2[1] and c2[4] > c1[1] and c2[1] < c1[4]

def is_bearish_engulfing(candles):
    c1, c2 = candles[-2], candles[-1]
    return c1[4] > c1[1] and c2[1] > c2[4] and c2[1] > c1[4] and c2[4] < c1[1]

# --- เปิดออเดอร์ ---
def open_position(direction):
    price = fetch_price()
    side = 'buy' if direction == 'long' else 'sell'
    params = {'tdMode': 'cross', 'ordType': 'market'}  # ไม่ใส่ posSide เพราะใช้ One-way Mode

    try:
        order = exchange.create_order(symbol, type='market', side=side, amount=position_size, params=params)
        entry_price = float(order['info'].get('fillPx', price))
        telegram(f"เปิด {side.upper()} {position_size} {symbol} ที่ราคา {entry_price}")
        return entry_price, order['id']
    except Exception as e:
        telegram(f"[ERROR เปิดออเดอร์] {e}")
        return None, None

# --- ติดตามสถานะ TP/SL ---
def monitor_position(entry_price, direction, order_id):
    global last_sl_time

    sl_buffer = 0.005  # SL 0.5%
    if direction == 'long':
        sl = entry_price * (1 - sl_buffer)
        tp = entry_price + (entry_price - sl)  # RR 1:1
    else:
        sl = entry_price * (1 + sl_buffer)
        tp = entry_price - (sl - entry_price)

    while True:
        price = fetch_price()

        if direction == 'long':
            if price <= sl:
                telegram(f"SL ทำงาน (Long)\nราคาลงถึง {price}\nขาดทุน\nปิด {order_id}")
                last_sl_time = datetime.utcnow()
                break
            elif price >= tp:
                telegram(f"TP ถึงเป้า (Long)\nราคาขึ้นถึง {price}\nกำไร\nปิด {order_id}")
                break

        else:  # short
            if price >= sl:
                telegram(f"SL ทำงาน (Short)\nราคาขึ้นถึง {price}\nขาดทุน\nปิด {order_id}")
                last_sl_time = datetime.utcnow()
                break
            elif price <= tp:
                telegram(f"TP ถึงเป้า (Short)\nราคาลงถึง {price}\nกำไร\nปิด {order_id}")
                break

        time.sleep(10)

# --- MAIN LOOP ---
def main():
    global last_sl_time
    telegram("เริ่มทำงาน: Safe OKX Bot (One-way Mode)")

    while True:
        try:
            now = datetime.utcnow()
            if last_sl_time and (now - last_sl_time).total_seconds() < cooldown_after_sl_minutes * 60:
                print("รอ cooldown หลัง SL")
                time.sleep(60)
                continue

            candles = fetch_candles()

            if is_bullish_engulfing(candles):
                entry_price, order_id = open_position('long')
                if entry_price:
                    monitor_position(entry_price, 'long', order_id)

            elif is_bearish_engulfing(candles):
                entry_price, order_id = open_position('short')
                if entry_price:
                    monitor_position(entry_price, 'short', order_id)

            time.sleep(30)

        except Exception as e:
            telegram(f"[ERROR LOOP] {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()               
