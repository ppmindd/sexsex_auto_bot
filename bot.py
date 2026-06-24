import os
import sqlite3
import random
import asyncio
from datetime import datetime, date

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7381851504]

START_BALANCE = 1_000_000
DAILY_REWARD = 500_000
RELIEF_AMOUNT = 1_000_000


# ================= DB =================
def conn():
    return sqlite3.connect("casino.db")


def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        last_checkin TEXT DEFAULT ''
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        amount INTEGER,
        balance_after INTEGER,
        time TEXT
    )
    """)

    c.commit()
    c.close()


def get_balance(uid):
    c = conn()
    cur = c.cursor()

    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        cur.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)",
                    (uid, START_BALANCE))
        c.commit()
        c.close()
        return START_BALANCE

    c.close()
    return row[0]


def set_balance(uid, amount):
    c = conn()
    cur = c.cursor()

    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        new = amount
        cur.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)",
                    (uid, amount))
    else:
        new = row[0] + amount
        cur.execute("UPDATE users SET balance=? WHERE user_id=?",
                    (new, uid))

    c.commit()
    c.close()
    return new


def log(uid, action, amount, bal):
    c = conn()
    cur = c.cursor()

    cur.execute("""
    INSERT INTO logs (user_id, action, amount, balance_after, time)
    VALUES (?, ?, ?, ?, ?)
    """, (uid, action, amount, bal, datetime.now().strftime("%H:%M:%S")))

    c.commit()
    c.close()


def is_admin(uid):
    return uid in ADMIN_IDS


# ================= BASIC =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_balance(uid)
    await update.message.reply_text("🎰 Casino Online\n💰 +1,000,000")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)
    await update.message.reply_text(f"💰 {bal:,}")


# ================= COIN ANIMATION =================
async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if len(context.args) < 2:
        return await update.message.reply_text("coin head/tail bet")

    choice = context.args[0]
    bet = int(context.args[1])

    bal = get_balance(uid)
    if bal < bet:
        return await update.message.reply_text("No money")

    msg = await update.message.reply_text("🪙 Flipping coin...")

    frames = ["🪙", "🪙.", "🪙..", "🪙..."]
    for f in frames:
        await asyncio.sleep(0.5)
        await msg.edit_text(f"Flipping {f}")

    result = random.choice(["head", "tail"])

    if choice == result:
        new = set_balance(uid, bet)
        log(uid, "coin_win", bet, new)
        await msg.edit_text(f"🟢 WIN ({result}) +{bet:,}")
    else:
        new = set_balance(uid, -bet)
        log(uid, "coin_loss", -bet, new)
        await msg.edit_text(f"🔴 LOSE ({result}) -{bet:,}")


# ================= DICE ANIMATION =================
async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bet = int(context.args[0])

    bal = get_balance(uid)
    if bal < bet:
        return

    msg = await update.message.reply_text("🎲 Rolling dice...")

    for i in range(5):
        await asyncio.sleep(0.4)
        await msg.edit_text(f"🎲 Rolling {'.' * (i+1)}")

    roll = random.randint(1, 6)

    if roll >= 4:
        new = set_balance(uid, bet)
        log(uid, "dice_win", bet, new)
        await msg.edit_text(f"🟢 {roll} WIN +{bet:,}")
    else:
        new = set_balance(uid, -bet)
        log(uid, "dice_loss", -bet, new)
        await msg.edit_text(f"🔴 {roll} LOSE -{bet:,}")


# ================= SLOT ANIMATION =================
async def slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bet = int(context.args[0])

    symbols = ["🍒", "🍋", "🔔", "⭐", "💎"]

    msg = await update.message.reply_text("🎰 Spinning slots...")

    for _ in range(6):
        r = [random.choice(symbols) for _ in range(3)]
        await asyncio.sleep(0.4)
        await msg.edit_text(f"🎰 {' | '.join(r)}")

    final = [random.choice(symbols) for _ in range(3)]

    if len(set(final)) == 1:
        win = bet * 5
        new = set_balance(uid, win)
        log(uid, "slot_jackpot", win, new)
        await msg.edit_text(f"💥 JACKPOT {final} +{win:,}")

    elif len(set(final)) == 2:
        win = bet * 2
        new = set_balance(uid, win)
        log(uid, "slot_win", win, new)
        await msg.edit_text(f"🟢 WIN {final} +{win:,}")

    else:
        new = set_balance(uid, -bet)
        log(uid, "slot_loss", -bet, new)
        await msg.edit_text(f"🔴 LOSE {final} -{bet:,}")


# ================= BACCARAT ANIMATION =================
async def baccarat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bet = int(context.args[0])

    msg = await update.message.reply_text("🃏 Dealing cards...")

    player = 0
    banker = 0

    for i in range(2):
        await asyncio.sleep(0.8)
        p = random.randint(1, 10)
        b = random.randint(1, 10)
        player += p
        banker += b
        await msg.edit_text(f"🃏 Player +{p} | Banker +{b}")

    await asyncio.sleep(1)

    if player > banker:
        new = set_balance(uid, bet)
        log(uid, "baccarat_win", bet, new)
        await msg.edit_text(f"🟢 PLAYER WIN {player} vs {banker} +{bet:,}")

    elif banker > player:
        new = set_balance(uid, -bet)
        log(uid, "baccarat_loss", -bet, new)
        await msg.edit_text(f"🔴 BANKER WIN {player} vs {banker} -{bet:,}")

    else:
        await msg.edit_text(f"⚪ DRAW {player} vs {banker}")


# ================= MAIN =================
def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))

    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("slot", slot))
    app.add_handler(CommandHandler("baccarat", baccarat))

    print("🔥 Casino Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()