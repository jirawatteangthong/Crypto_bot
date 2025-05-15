import ccxt
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

# ====== Config =======
API_KEY = "8f528085-448c-4480-a2b0-d7f72afb38ad"
API_SECRET = "05A665CEAF8B2161483DF63CB10085D2"
API_PASSPHRASE = "Jirawat1-"
TELEGRAM_BOT_TOKEN = "7752789264:AAF-0zdgHsSSYe7PS17ePYThOFP3k7AjxBY"
TELEGRAM_CHAT_ID = "8104629569"
SYMBOL = "BTC-USDT-SWAP"
TIMEFRAME = "5m"
LOT_SIZE = 0.7
MAX_TRADES_PER_DAY = 5

exchange = ccxt.okx({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'password': API_PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'},
})

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.post(url, data=payload)
    except:
        pass

def fetch_ohlcv(limit=500):
    try:
        data = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=limit)
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print("Fetch OHLCV error:", e)
        return None

def detect_swings(df):
    df["swing_high"] = df["high"][(df["high"].shift(1) < df["high"]) & (df["high"].shift(-1) < df["high"])]
    df["swing_low"] = df["low"][(df["low"].shift(1) > df["low"]) & (df["low"].shift(-1) > df["low"])]
    return df

def detect_bos_ob(df):
    df = detect_swings(df)
    structures = []
    for i in range(10, len(df)):
        row = df.iloc[i]
        recent_highs = df.iloc[i-10:i]["swing_high"].dropna()
        recent_lows = df.iloc[i-10:i]["swing_low"].dropna()

        if not recent_highs.empty and row["close"] > recent_highs.max():
            ob_row = df.iloc[i-1]
            structures.append({
                "time": row["datetime"],
                "type": "BOS_UP",
                "ob_high": ob_row["high"],
                "ob_low": ob_row["low"]
            })

        elif not recent_lows.empty and row["close"] < recent_lows.min():
            ob_row = df.iloc[i-1]
            structures.append({
                "time": row["datetime"],
                "type": "BOS_DOWN",
                "ob_high": ob_row["high"],
                "ob_low": ob_row["low"]
            })

    return pd.DataFrame(structures)

def get_open_position_count():
    try:
        positions = exchange.fetch_positions([SYMBOL])
        for p in positions:
            if float(p['contracts']) > 0:
                return 1
        return 0
    except:
        return 0

def get_available_margin():
    try:
        balance = exchange.fetch_balance()
        return balance['USDT']['free']
    except:
        return 0

def place_order(side, amount):
    try:
        order = exchange.create_order(SYMBOL, 'market', side, amount)
        send_telegram(f"เปิด {side} ออเดอร์ จำนวน {amount} {SYMBOL} ที่ราคา market")
        return order
    except Exception as e:
        send_telegram(f"เกิดข้อผิดพลาดตอนเปิดออเดอร์: {e}")
        return None

def close_order(order_id):
    try:
        positions = exchange.fetch_positions([SYMBOL])
        for p in positions:
            if float(p['contracts']) > 0:
                side = 'sell' if p['side'] == 'long' else 'buy'
                amount = float(p['contracts'])
                exchange.create_order(SYMBOL, 'market', side, amount)
                send_telegram(f"ปิดออเดอร์ {order_id} แล้ว")
                return True
        return False
    except Exception as e:
        send_telegram(f"เกิดข้อผิดพลาดตอนปิดออเดอร์: {e}")
        return False

def generate_trade_signals(df, bos_df):
    trades = []
    now = datetime.utcnow()

    for idx, bos in bos_df.iterrows():
        ob_high = bos["ob_high"]
        ob_low = bos["ob_low"]
        entry_time = bos["time"]
        direction = "buy" if bos["type"] == "BOS_UP" else "sell"

        df_after = df[df["datetime"] > entry_time]

        for i, row in df_after.iterrows():
            if direction == "buy" and ob_low <= row["low"] <= ob_high:
                entry_price = row["close"]
                sl = ob_low * 0.999
                tp = entry_price + 2 * (entry_price - sl)
                trades.append({"direction": direction, "entry_price": entry_price, "sl": sl, "tp": tp})
                break
            elif direction == "sell" and ob_low <= row["high"] <= ob_high:
                entry_price = row["close"]
                sl = ob_high * 1.001
                tp = entry_price - 2 * (sl - entry_price)
                trades.append({"direction": direction, "entry_price": entry_price, "sl": sl, "tp": tp})
                break

    return trades

def main_loop():
    send_telegram("บอท ICT-SMC เริ่มทำงานแล้ว")
    open_trade = None
    trade_sl = trade_tp = 0

    while True:
        df = fetch_ohlcv()
        if df is None or df.empty:
            time.sleep(60)
            continue

        bos_df = detect_bos_ob(df)
        signals = generate_trade_signals(df, bos_df)

        if open_trade is None:
            if get_open_position_count() > 0:
                time.sleep(60)
                continue
            if get_available_margin() < 30:
                send_telegram("ทุนไม่พอสำหรับเปิดออเดอร์ใหม่")
                time.sleep(60)
                continue
            if signals:
                sig = signals[0]
                side = sig["direction"]
                trade_sl = sig["sl"]
                trade_tp = sig["tp"]
                order = place_order(side, LOT_SIZE)
                if order:
                    open_trade = {
                        "order_id": order["id"],
                        "side": side,
                        "sl": trade_sl,
                        "tp": trade_tp
                    }

        else:
            last_price = df.iloc[-1]['close']
            if open_trade["side"] == "buy":
                if last_price >= open_trade["tp"]:
                    send_telegram("TP ทำงาน ออเดอร์กำไร")
                    close_order(open_trade["order_id"])
                    open_trade = None
                elif last_price <= open_trade["sl"]:
                    send_telegram("SL ทำงาน ออเดอร์ขาดทุน")
                    close_order(open_trade["order_id"])
                    open_trade = None
            else:
                if last_price <= open_trade["tp"]:
                    send_telegram("TP ทำงาน ออเดอร์กำไร")
                    close_order(open_trade["order_id"])
                    open_trade = None
                elif last_price >= open_trade["sl"]:
                    send_telegram("SL ทำงาน ออเดอร์ขาดทุน")
                    close_order(open_trade["order_id"])
                    open_trade = None

        time.sleep(60)

if __name__ == "__main__":
    main_loop()
