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
    await update.message.reply_text("🎰 Casino Online\n💰 +1,000,000 loaded")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)
    await update.message.reply_text(f"💰 Balance: {bal:,}")


# ================= CHECKIN =================
async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today = str(date.today())

    c = conn()
    cur = c.cursor()
    cur.execute("SELECT last_checkin FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if row and row[0] == today:
        return await update.message.reply_text("❌ Already claimed today")

    new = set_balance(uid, DAILY_REWARD)

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?",
                (today, uid))
    c.commit()
    c.close()

    log(uid, "checkin", DAILY_REWARD, new)

    await update.message.reply_text(f"🎁 +{DAILY_REWARD:,}")


# ================= RELIEF =================
async def relief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)

    if bal > 0:
        return await update.message.reply_text("❌ Only 0 balance users")

    new = set_balance(uid, RELIEF_AMOUNT)
    log(uid, "relief", RELIEF_AMOUNT, new)

    await update.message.reply_text(f"🆘 +{RELIEF_AMOUNT:,}")


# ================= TRANSFER =================
async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /transfer id amount")

    target = int(context.args[0])
    amt = int(context.args[1])

    bal = get_balance(uid)
    if bal < amt:
        return await update.message.reply_text("No money")

    set_balance(uid, -amt)
    new_target = set_balance(target, amt)

    log(uid, "transfer_out", -amt, bal - amt)
    log(target, "transfer_in", amt, new_target)

    await update.message.reply_text("✅ Transfer done")


# ================= ADMIN =================
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("No permission")

    await update.message.reply_text(
        "/addmoney\n/removemoney\n/logs\n/rank"
    )


async def addmoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    uid = int(context.args[0])
    amt = int(context.args[1])

    new = set_balance(uid, amt)
    log(uid, "admin_add", amt, new)

    await update.message.reply_text("Added")


async def removemoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    uid = int(context.args[0])
    amt = int(context.args[1])

    new = set_balance(uid, -amt)
    log(uid, "admin_remove", -amt, new)

    await update.message.reply_text("Removed")


# ================= LOGS =================
async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    c = conn()
    cur = c.cursor()

    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()

    text = "📜 LOGS\n\n"
    for r in rows:
        text += f"{r[1]} | {r[2]} | {r[3]} | {r[4]}\n"

    await update.message.reply_text(text)


# ================= RANK =================
async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = conn()
    cur = c.cursor()

    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()

    text = "🏆 RANK TOP 10\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r[0]} - {r[1]:,}\n"

    await update.message.reply_text(text)


# ================= 🎰 SLOT ANIMATION =================
async def slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bet = int(context.args[0])

    symbols = ["🍒", "🍋", "🔔", "⭐", "💎"]

    msg = await update.message.reply_text("🎰 Spinning...")

    for _ in range(5):
        r = [random.choice(symbols) for _ in range(3)]
        await asyncio.sleep(0.5)
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


# ================= 🪙 COIN ANIMATION =================
async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    choice = context.args[0]
    bet = int(context.args[1])

    msg = await update.message.reply_text("🪙 Flipping...")

    frames = ["🪙", "🪙.", "🪙..", "🪙..."]
    for f in frames:
        await asyncio.sleep(0.4)
        await msg.edit_text(f"Flipping {f}")

    result = random.choice(["head", "tail"])

    if choice == result:
        new = set_balance(uid, bet)
        log(uid, "coin_win", bet, new)
        await msg.edit_text(f"🟢 WIN {result} +{bet:,}")
    else:
        new = set_balance(uid, -bet)
        log(uid, "coin_loss", -bet, new)
        await msg.edit_text(f"🔴 LOSE {result} -{bet:,}")


# ================= 🎲 DICE =================
async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bet = int(context.args[0])

    msg = await update.message.reply_text("🎲 Rolling...")

    for i in range(4):
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


# ================= MAIN =================
def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("relief", relief))
    app.add_handler(CommandHandler("transfer", transfer))

    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addmoney", addmoney))
    app.add_handler(CommandHandler("removemoney", removemoney))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("rank", rank))

    app.add_handler(CommandHandler("slot", slot))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("dice", dice))

    print("🎰 FULL CASINO BOT RUNNING")
    app.run_polling()


if __name__ == "__main__":
    main()