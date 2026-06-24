import os
import sqlite3
import random
from datetime import datetime, date

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [7381851504]

START_BALANCE = 1000000
DAILY_REWARD = 500000


# ---------------- ADMIN ----------------
def is_admin(user_id):
    return user_id in ADMIN_IDS


# ---------------- DB ----------------
def init_db():
    conn = sqlite3.connect("casino.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        last_checkin TEXT DEFAULT '',
        last_relief TEXT DEFAULT ''
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

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect("casino.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, START_BALANCE)
        )
        conn.commit()
        conn.close()
        return (user_id, START_BALANCE, "", "")

    conn.close()
    return row


def update_balance(user_id, amount):
    conn = sqlite3.connect("casino.db")
    cur = conn.cursor()

    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, amount)
        )
    else:
        new_balance = row[0] + amount
        cur.execute(
            "UPDATE users SET balance=? WHERE user_id=?",
            (new_balance, user_id)
        )

    conn.commit()
    conn.close()


def log_action(user_id, action, amount, balance_after):
    conn = sqlite3.connect("casino.db")
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO logs (user_id, action, amount, balance_after, time)
    VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        action,
        amount,
        balance_after,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    get_user(user_id)

    await update.message.reply_text(
        f"🎰 Casino Bot Started\n+{START_BALANCE:,} coins"
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    await update.message.reply_text(f"💰 Balance: {user[1]:,}")


# ---------------- TRANSFER ----------------
async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /transfer <user_id> <amount>")
        return

    target_id = int(context.args[0])
    amount = int(context.args[1])

    sender = get_user(sender_id)

    if amount <= 0 or sender[1] < amount:
        await update.message.reply_text("Invalid amount")
        return

    update_balance(sender_id, -amount)
    update_balance(target_id, amount)

    await update.message.reply_text(
        f"Transfer done\nTo: {target_id}\nAmount: {amount:,}"
    )


# ---------------- ADMIN ----------------
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No permission")
        return

    await update.message.reply_text(
        "/addmoney /removemoney /logs /rank"
    )


async def addmoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    target_id = int(context.args[0])
    amount = int(context.args[1])

    update_balance(target_id, amount)
    await update.message.reply_text("Added money")


async def removemoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    target_id = int(context.args[0])
    amount = int(context.args[1])

    update_balance(target_id, -amount)
    await update.message.reply_text("Removed money")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect("casino.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()

    text = "LOGS\n\n"
    for r in rows:
        text += f"{r[5]} | UID:{r[1]} | {r[2]} | {r[3]} | {r[4]}\n"

    await update.message.reply_text(text)


async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("casino.db")
    cur = conn.cursor()

    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()

    text = "RANKING\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r[0]} - {r[1]:,}\n"

    await update.message.reply_text(text)


# ---------------- GAMES ----------------
async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /dice <bet>")
        return

    bet = int(context.args[0])

    if bet <= 0 or user[1] < bet:
        await update.message.reply_text("Invalid bet")
        return

    roll = random.randint(1, 6)

    if roll >= 4:
        update_balance(user_id, bet)
        msg = "WIN"
    else:
        update_balance(user_id, -bet)
        msg = "LOSE"

    await update.message.reply_text(f"{roll}\n{msg}")


async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /coin <bet> head|tail")
        return

    bet = int(context.args[0])
    choice = context.args[1].lower()

    if choice not in ["head", "tail"]:
        return

    if user[1] < bet:
        return

    result = random.choice(["head", "tail"])

    if result == choice:
        update_balance(user_id, bet)
        msg = "WIN"
    else:
        update_balance(user_id, -bet)
        msg = "LOSE"

    await update.message.reply_text(f"{result}\n{msg}")


# ---------------- SLOT ----------------
symbols = ["🍒", "🍋", "🍇", "💎", "7️⃣"]

async def slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /slot <bet>")
        return

    bet = int(context.args[0])

    if bet <= 0 or user[1] < bet:
        return

    reels = [random.choice(symbols) for _ in range(3)]

    if reels[0] == reels[1] == reels[2]:
        reward = bet * 5
        update_balance(user_id, reward)
        result = "JACKPOT"
    else:
        update_balance(user_id, -bet)
        result = "LOSE"

    await update.message.reply_text(f"{' '.join(reels)}\n{result}")


# ---------------- MAIN ----------------
def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("transfer", transfer))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addmoney", addmoney))
    app.add_handler(CommandHandler("removemoney", removemoney))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("slot", slot))

    app.run_polling()


if __name__ == "__main__":
    main()