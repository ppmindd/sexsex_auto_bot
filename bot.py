import os
import sqlite3
import random
import asyncio
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7381851504]

START_BALANCE = 1_000_000
DAILY_REWARD = 300_000
RELIEF_AMOUNT = 500_000


# ================= DB =================
def conn():
    return sqlite3.connect("casino.db", check_same_thread=False)


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


# ================= SAFE CORE =================
def get_balance(uid):
    c = conn()
    cur = c.cursor()

    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        cur.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (uid, START_BALANCE))
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
        cur.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (uid, amount))
    else:
        new = row[0] + amount
        cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new, uid))

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


# ================= UI =================
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Balance", callback_data="bal")],
        [InlineKeyboardButton("🎰 Slot", callback_data="slot")],
        [InlineKeyboardButton("🪙 Coin", callback_data="coin")],
        [InlineKeyboardButton("🎲 Dice", callback_data="dice")],
        [InlineKeyboardButton("🃏 Baccarat", callback_data="baccarat")],
        [InlineKeyboardButton("💸 Transfer", callback_data="transfer")],
        [InlineKeyboardButton("🎁 Checkin", callback_data="checkin")],
        [InlineKeyboardButton("🆘 Relief", callback_data="relief")],
        [InlineKeyboardButton("🏆 Rank", callback_data="rank")],
        [InlineKeyboardButton("🛠 Admin", callback_data="admin")]
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add", callback_data="add")],
        [InlineKeyboardButton("➖ Remove", callback_data="remove")],
        [InlineKeyboardButton("📜 Logs", callback_data="logs")],
        [InlineKeyboardButton("🏠 Home", callback_data="home")]
    ])


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_balance(uid)
    await update.message.reply_text("💎 CASINO ONLINE", reply_markup=menu())


# ================= CALLBACK =================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    # HOME
    if q.data == "home":
        return await q.edit_message_text("🏠 MENU", reply_markup=menu())

    # BALANCE
    if q.data == "bal":
        return await q.edit_message_text(f"💰 {get_balance(uid):,}", reply_markup=menu())

    # CHECKIN
    if q.data == "checkin":
        today = str(date.today())
        c = conn()
        cur = c.cursor()

        cur.execute("SELECT last_checkin FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()

        if row and row[0] == today:
            return await q.edit_message_text("❌ Already claimed")

        new = set_balance(uid, DAILY_REWARD)

        cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (today, uid))
        c.commit()
        c.close()

        log(uid, "checkin", DAILY_REWARD, new)
        return await q.edit_message_text(f"🎁 +{DAILY_REWARD:,}")

    # RELIEF
    if q.data == "relief":
        if get_balance(uid) > 0:
            return await q.edit_message_text("❌ Only 0 balance allowed")

        new = set_balance(uid, RELIEF_AMOUNT)
        log(uid, "relief", RELIEF_AMOUNT, new)
        return await q.edit_message_text(f"🆘 +{RELIEF_AMOUNT:,}")

    # RANK
    if q.data == "rank":
        c = conn()
        cur = c.cursor()
        cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        rows = cur.fetchall()

        text = "🏆 RANK\n\n"
        for i, r in enumerate(rows, 1):
            text += f"{i}. {r[0]} → {r[1]:,}\n"

        return await q.edit_message_text(text, reply_markup=menu())

    # ADMIN
    if q.data == "admin":
        if not is_admin(uid):
            return await q.edit_message_text("❌ No permission")
        return await q.edit_message_text("🛠 ADMIN", reply_markup=admin_menu())

    # LOGS
    if q.data == "logs":
        if not is_admin(uid):
            return await q.edit_message_text("❌ No permission")

        c = conn()
        cur = c.cursor()
        cur.execute("SELECT user_id, action, amount, balance_after FROM logs ORDER BY id DESC LIMIT 5")
        rows = cur.fetchall()

        text = "📜 LOGS\n\n"
        for r in rows:
            text += f"{r[0]} | {r[1]} | {r[2]} | {r[3]}\n"

        return await q.edit_message_text(text, reply_markup=admin_menu())

    # SLOT
    if q.data == "slot":
        msg = await q.edit_message_text("🎰 Spinning...")

        symbols = ["🍒", "🍋", "🔔", "⭐", "💎"]

        for _ in range(4):
            await asyncio.sleep(0.4)
            r = [random.choice(symbols) for _ in range(3)]
            await msg.edit_text("🎰 " + " | ".join(r))

        final = [random.choice(symbols) for _ in range(3)]
        bet = 50000

        if len(set(final)) == 1:
            win = bet * 5
            new = set_balance(uid, win)
            log(uid, "slot_win", win, new)
            return await msg.edit_text(f"💥 JACKPOT {final} +{win:,}")

        if random.random() < 0.45:
            win = bet * 2
            new = set_balance(uid, win)
            log(uid, "slot_win", win, new)
            return await msg.edit_text(f"🟢 WIN {final} +{win:,}")

        new = set_balance(uid, -bet)
        log(uid, "slot_loss", -bet, new)
        return await msg.edit_text(f"🔴 LOSE {final} -{bet:,}")

    # COIN
    if q.data == "coin":
        msg = await q.edit_message_text("🪙 Flipping...")

        for i in range(4):
            await asyncio.sleep(0.3)
            await msg.edit_text("🪙" + "." * i)

        result = random.choice(["head", "tail"])
        return await msg.edit_message_text(f"🪙 {result}")

    # DICE
    if q.data == "dice":
        return await q.edit_message_text(f"🎲 {random.randint(1,6)}")

    # BACCARAT
    if q.data == "baccarat":
        p = random.randint(1, 10)
        b = random.randint(1, 10)

        if p > b:
            res = "PLAYER WIN"
        elif b > p:
            res = "BANKER WIN"
        else:
            res = "DRAW"

        return await q.edit_message_text(f"🃏 P:{p} B:{b}\n{res}")


# ================= ADMIN =================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
    except:
        return await update.message.reply_text("Usage: /addmoney id amount")

    new = set_balance(uid, amt)
    log(uid, "admin_add", amt, new)

    await update.message.reply_text(f"➕ {amt:,} → {uid}")


async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
    except:
        return await update.message.reply_text("Usage: /removemoney id amount")

    new = set_balance(uid, -amt)
    log(uid, "admin_remove", -amt, new)

    await update.message.reply_text(f"➖ {amt:,} → {uid}")


# ================= MAIN =================
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(CommandHandler("addmoney", add))
    app.add_handler(CommandHandler("removemoney", remove))

    print("💎 CASINO READY (STABLE)")
    app.run_polling()


if __name__ == "__main__":
    main()