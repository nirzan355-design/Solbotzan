import json
import threading
import time
import requests
import websocket
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8620442728:AAFJHgp2RHusLM3e1HYKzees5hGjogJ_6Rc"
CHAT_ID = "1667242955"

prices = {"BTCUSDT": None, "SOLUSDT": None}
last_update = 0
last_signal_hour = None

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=10
    )

def ws_message(ws, message):
    global last_update
    data = json.loads(message)
    d = data["data"]
    prices[d["s"]] = float(d["p"])
    last_update = time.time()

def run_ws():
    url = "wss://fstream.binance.com/stream?streams=btcusdt@trade/solusdt@trade"
    ws = websocket.WebSocketApp(url, on_message=ws_message)
    ws.run_forever()

def get_klines(symbol):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": "1h", "limit": 220}
    data = requests.get(url, params=params, timeout=10).json()
    closes = [float(x[4]) for x in data]
    highs = [float(x[2]) for x in data]
    lows = [float(x[3]) for x in data]
    return closes, highs, lows

def ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def build_signal():
    btc_close, _, _ = get_klines("BTCUSDT")
    sol_close, sol_high, sol_low = get_klines("SOLUSDT")

    btc_ema50 = ema(btc_close[-200:], 50)
    btc_ema200 = ema(btc_close[-220:], 200)

    sol_ema20 = ema(sol_close[-80:], 20)
    sol_ema50 = ema(sol_close[-100:], 50)
    sol_rsi = rsi(sol_close)

    entry = sol_close[-1]
    recent_low = min(sol_low[-10:])
    recent_high = max(sol_high[-10:])

    long_score = 0
    short_score = 0

    if btc_ema50 > btc_ema200:
        long_score += 30
    else:
        short_score += 30

    if sol_ema20 > sol_ema50:
        long_score += 30
    else:
        short_score += 30

    if 45 <= sol_rsi <= 70:
        long_score += 25

    if 30 <= sol_rsi <= 55:
        short_score += 25

    if entry > sol_ema20:
        long_score += 15
    else:
        short_score += 15

    if long_score > short_score and long_score >= 65:
        direction = "🟢 LONG"
        probability = min(long_score, 80)
        sl = recent_low * 0.995
        risk = entry - sl
        tp1 = entry + risk
        tp2 = entry + risk * 2
        tp3 = entry + risk * 3

    elif short_score > long_score and short_score >= 65:
        direction = "🔴 SHORT"
        probability = min(short_score, 80)
        sl = recent_high * 1.005
        risk = sl - entry
        tp1 = entry - risk
        tp2 = entry - risk * 2
        tp3 = entry - risk * 3

    else:
        return f"""
⚪ NO TRADE / WAIT

TF: 1H
SOL Price: ${entry:.2f}
RSI: {sol_rsi:.2f}

LONG Score: {long_score}%
SHORT Score: {short_score}%

Market belum jelas.
"""

    rr = abs(tp2 - entry) / abs(entry - sl)

    return f"""
{direction} SOLUSDT

Probability: {probability}%

TF: 1H
Entry: ${entry:.2f}

Stop Loss: ${sl:.2f}

TP1: ${tp1:.2f}
TP2: ${tp2:.2f}
TP3: ${tp3:.2f}

Risk Reward TP2: 1:{rr:.2f}

BTC EMA50: {btc_ema50:.2f}
BTC EMA200: {btc_ema200:.2f}

SOL EMA20: {sol_ema20:.2f}
SOL EMA50: {sol_ema50:.2f}
RSI: {sol_rsi:.2f}

Catatan: ini alert indikator, bukan jaminan profit.
"""

def auto_signal():
    global last_signal_hour

    while True:
        now = time.localtime()

        if now.tm_min == 0:
            current_hour = now.tm_hour

            if current_hour != last_signal_hour:
                last_signal_hour = current_hour

                try:
                    text = "⏰ AUTO SIGNAL 1H\n" + build_signal()
                    send_telegram(text)
                    print("Auto signal terkirim")
                except Exception as e:
                    print("Auto signal error:", e)

        time.sleep(30)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ BOT ONLINE\n\n"
        "/status\n"
        "/price\n"
        "/btc\n"
        "/sol\n"
        "/signal"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    online = time.time() - last_update < 10
    bot_status = "ONLINE ✅" if online else "OFFLINE ⚠️"

    btc = prices["BTCUSDT"]
    sol = prices["SOLUSDT"]

    btc_text = f"${btc:,.2f}" if btc else "belum ada data"
    sol_text = f"${sol:,.2f}" if sol else "belum ada data"

    await update.message.reply_text(
        f"📡 STATUS BOT\n\n"
        f"Bot: {bot_status}\n\n"
        f"BTCUSDT: {btc_text}\n"
        f"SOLUSDT: {sol_text}\n\n"
        f"Auto Signal: ON ✅"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btc = prices["BTCUSDT"]
    sol = prices["SOLUSDT"]

    btc_text = f"${btc:,.2f}" if btc else "belum ada data"
    sol_text = f"${sol:,.2f}" if sol else "belum ada data"

    await update.message.reply_text(
        f"💰 PRICE\n\nBTCUSDT: {btc_text}\nSOLUSDT: {sol_text}"
    )

async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btc = prices["BTCUSDT"]
    await update.message.reply_text(f"₿ BTCUSDT: ${btc:,.2f}" if btc else "Belum ada data BTC")

async def sol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sol = prices["SOLUSDT"]
    await update.message.reply_text(f"🪙 SOLUSDT: ${sol:,.2f}" if sol else "Belum ada data SOL")

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Analisis 1H BTC + SOL...")
    try:
        await update.message.reply_text(build_signal())
    except Exception as e:
        await update.message.reply_text(f"Error signal: {e}")

threading.Thread(target=run_ws, daemon=True).start()
threading.Thread(target=auto_signal, daemon=True).start()

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("btc", btc))
app.add_handler(CommandHandler("sol", sol))
app.add_handler(CommandHandler("signal", signal))

print("Bot running...")
app.run_polling()
