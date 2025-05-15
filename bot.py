import ccxt
import time
import requests
from datetime import datetime, timedelta

# ตั้งค่า OKX API
api_key = '8f528085-448c-4480-a2b0-d7f72afb38ad'
secret = '05A665CEAF8B2161483DF63CB10085D2'
password = 'Jirawat1-'

symbol = 'BTC/USDT:USDT'
position_size = 0.7
cooldown_after_sl_minutes = 5

# Telegram แจ้งเตือน
telegram_token = '7752789264:AAF-0zdgHsSSYe7PS17ePYThOFP3k7AjxBY'
telegram_chat_id = '8104629569'

def telegram(message):
    requests.get(f'https://api.telegram.org/bot{telegram_token}/sendMessage',
                 params={'chat_id': telegram_chat_id, 'text': message})

# เชื่อมต่อ OKX
exchange = ccxt.okx({
    'apiKey': api_key,
    'secret': secret,
    'password': password,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})
exchange.set_sandbox_mode(False)  # เปลี่ยนเป็น True ถ้าจะทดสอบก่อน

last_sl_time = None

def fetch_price():
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker['last'])

def fetch_candles():
    candles = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=3)
    return candles

def is_bullish_engulfing(candles):
    c1, c2 = candles[-2], candles[-1]
    return c1[1] > c1[4] and c2[4] > c2[1] and c2[4] > c1[1] and c2[1] < c1[4]

def open_position(direction):
    price = fetch_price()
    side = 'buy' if direction == 'long' else 'sell'
    params = {'tdMode': 'cross', 'side': side, 'ordType': 'market', 'posSide': direction}
    
    try:
        order = exchange.create_order(symbol, type='market', side=side, amount=position_size, params=params)
        entry_price = float(order['info'].get('fillPx', price))
        telegram(f"เปิด {side.upper()} {position_size} {symbol} ที่ราคา {entry_price}")
        return entry_price, order['id']
    except Exception as e:
        telegram(f"[ERROR เปิดออเดอร์] {e}")
        return None, None

def monitor_position(entry_price, sl_price, tp_price, direction, order_id):
    global last_sl_time

    while True:
        price = fetch_price()

        if direction == 'long':
            if price <= sl_price:
                telegram(f"SL ทำงาน ออเดอร์ขาดทุน\nปิดออเดอร์ {order_id}")
                last_sl_time = datetime.utcnow()
                break
            elif price >= tp_price:
                telegram(f"TP ถึงเป้า ออเดอร์กำไร\nปิดออเดอร์ {order_id}")
                break
        else:
            if price >= sl_price:
                telegram(f"SL ทำงาน ออเดอร์ขาดทุน\nปิดออเดอร์ {order_id}")
                last_sl_time = datetime.utcnow()
                break
            elif price <= tp_price:
                telegram(f"TP ถึงเป้า ออเดอร์กำไร\nปิดออเดอร์ {order_id}")
                break

        time.sleep(10)

def main():
    global last_sl_time

    while True:
        try:
            now = datetime.utcnow()

            # ถ้าเพิ่ง SL ให้รอ cooldown
            if last_sl_time and (now - last_sl_time).total_seconds() < cooldown_after_sl_minutes * 60:
                print("รอ cooldown หลัง SL")
                time.sleep(60)
                continue

            candles = fetch_candles()

            if is_bullish_engulfing(candles):
                entry_price, order_id = open_position('long')
                if entry_price:
                    sl = entry_price * 0.997  # SL ห่าง 0.3%
                    tp = entry_price + (entry_price - sl)  # RR 1:1
                    monitor_position(entry_price, sl, tp, 'long', order_id)

            time.sleep(30)

        except Exception as e:
            telegram(f"[ERROR LOOP] {e}")
            time.sleep(60)

if __name__ == "__main__":
    telegram("เริ่มทำงาน: Safe OKX Bot")
    main()
