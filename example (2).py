# main.py
from flask import Flask
import threading
import time

app = Flask(__name__)

# ตัวอย่างงานที่รันเบื้องหลัง (สามารถใส่บอทเทรดที่นี่ได้)
def run_bot():
    while True:
        print("บอททำงานอยู่...")
        time.sleep(10)

@app.route('/')
def home():
    return "บอทรันอยู่แล้วจ้า!"

# สั่งให้รันบอทแบบเบื้องหลัง
if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=3000)
