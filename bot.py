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
LOT_SIZE = 0.1
MAX_TRADES_PER_DAY = 5

exchange = ccxt.okx({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'password': API_PASSPHRASE,
    'enableRateLimit': True,
})

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram send error:", e)

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
    last_high = None
    last_low = None

    for i in range(10, len(df)):
        row = df.iloc[i]
        recent_highs = df.iloc[i-10:i]["swing_high"].dropna()
        recent_lows = df.iloc[i-10:i]["swing_low"].dropna()

        if not recent_highs.empty:
            last_high = recent_highs.iloc[-1]
        if not recent_lows.empty:
            last_low = recent_lows.iloc[-1]

        if last_high and row["close"] > last_high:
            ob_row = df.iloc[i-1]
            structures.append({
                "time": row["datetime"],
                "type": "BOS_UP",
                "bos_price": row["close"],
                "ob_time": ob_row["datetime"],
                "ob_high": ob_row["high"],
                "ob_low": ob_row["low"]
            })

        elif last_low and row["close"] < last_low:
            ob_row = df.iloc[i-1]
            structures.append({
                "time": row["datetime"],
                "type": "BOS_DOWN",
                "bos_price": row["close"],
                "ob_time": ob_row["datetime"],
                "ob_high": ob_row["high"],
                "ob_low": ob_row["low"]
            })

    return pd.DataFrame(structures)

def backtest_live_logic(df, bos_df):
    trades = []
    daily_trades = {}
    now = datetime.utcnow()

    for idx, bos in bos_df.iterrows():
        trade_day = bos["time"].date()
        if trade_day not in daily_trades:
            daily_trades[trade_day] = 0
        if daily_trades[trade_day] >= MAX_TRADES_PER_DAY:
            continue

        ob_high = bos["ob_high"]
        ob_low = bos["ob_low"]
        entry_time = bos["time"]
        direction = "buy" if bos["type"] == "BOS_UP" else "sell"

        df_after_bos = df[df["datetime"] > entry_time]

        entry_index = None
        for i, row in df_after_bos.iterrows():
            if direction == "buy" and ob_low <= row["low"] <= ob_high:
                entry_index = i
                break
            elif direction == "sell" and ob_low <= row["high"] <= ob_high:
                entry_index = i
                break

        if entry_index is None:
            continue

        entry_row = df.loc[entry_index]
        entry_price = entry_row["close"]
        entry_time = entry_row["datetime"]

        if direction == "buy":
            sl = ob_low * 0.999  # SL ใต้ OB เล็กน้อย
            tp = entry_price + 2 * (entry_price - sl)  # TP RR 1:2
        else:
            sl = ob_high * 1.001  # SL เหนือ OB เล็กน้อย
            tp = entry_price - 2 * (sl - entry_price)  # TP RR 1:2

        trades.append({
            "entry_time": entry_time,
            "direction": direction,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
        })
        daily_trades[trade_day] += 1
        if sum(daily_trades.values()) >= MAX_TRADES_PER_DAY:
            break

    return trades

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
        # ปิดตำแหน่งตลาดทันที
        pos = exchange.fetch_positions([SYMBOL])
        for p in pos:
            if p['info']['posId'] == order_id:
                side = 'sell' if p['side'] == 'long' else 'buy'
                amount = p['contracts']
                exchange.create_order(SYMBOL, 'market', side, amount)
                send_telegram(f"ปิดออเดอร์ {order_id} แล้ว")
                return True
        return False
    except Exception as e:
        send_telegram(f"เกิดข้อผิดพลาดตอนปิดออเดอร์: {e}")
        return False

def main_loop():
    send_telegram("บอท ICT-SMC เริ่มทำงาน")
    open_trades = []

    while True:
        df = fetch_ohlcv()
        if df is None or df.empty:
            time.sleep(60)
            continue

        bos_df = detect_bos_ob(df)
        trade_signals = backtest_live_logic(df, bos_df)

        # เปิดออเดอร์ใหม่ถ้าไม่มีออเดอร์เปิดอยู่
        if len(open_trades) < MAX_TRADES_PER_DAY:
            for signal in trade_signals:
                side = signal['direction']
                order = place_order(side, LOT_SIZE)
                if order:
                    signal['order_id'] = order['id']
                    signal['status'] = 'open'
                    open_trades.append(signal)
                time.sleep(1)

        # ตรวจสอบ TP/SL และปิดออเดอร์ (simplified)
        for trade in open_trades[:]:
            # ดึงข้อมูลราคา realtime ล่าสุด
            last_price = df.iloc[-1]['close']
            if trade['direction'] == 'buy':
                if last_price >= trade['tp']:
                    send_telegram(f"TP ถูกทำงานสำหรับออเดอร์ {trade['order_id']} กำไร")
                    close_order(trade['order_id'])
                    open_trades.remove(trade)
                elif last_price <= trade['sl']:
                    send_telegram(f"SL ถูกทำงานสำหรับออเดอร์ {trade['order_id']} ขาดทุน")
                    close_order(trade['order_id'])
                    open_trades.remove(trade)
            else:
                if last_price <= trade['tp']:
                    send_telegram(f"TP ถูกทำงานสำหรับออเดอร์ {trade['order_id']} กำไร")
                    close_order(trade['order_id'])
                    open_trades.remove(trade)
                elif last_price >= trade['sl']:
                    send_telegram(f"SL ถูกทำงานสำหรับออเดอร์ {trade['order_id']} ขาดทุน")
                    close_order(trade['order_id'])
                    open_trades.remove(trade)

        time.sleep(60)  # รันทุก 1 นาที

if __name__ == "__main__":
    main_loop()
