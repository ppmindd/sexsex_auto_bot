import os
import sqlite3
import random
import logging
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ======================
# CONFIG
# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {123456789}  # 👈 본인 Telegram ID로 변경 필수

logging.basicConfig(level=logging.INFO)

# ======================
# DB
# ======================
conn = sqlite3.connect("casino.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 1000,
    last_checkin TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    amount INTEGER,
    balance INTEGER,
    timestamp TEXT
)
""")

conn.commit()

# ======================
# DB HELPERS
# ======================
def get_user(user_id):
    cur.execute("SELECT user_id, balance, last_checkin FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, 10000)  # 🔥 초기 자본 수정됨
        )
        conn.commit()
        return (user_id, 10000, None)

    return row


def log_action(user_id, action, amount, balance):
    cur.execute(
        "INSERT INTO logs (user_id, action, amount, balance, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, amount, balance, datetime.now().isoformat()),
    )
    conn.commit()


def update_balance(user_id, amount):
    user = get_user(user_id)
    new_balance = user[1] + amount

    if new_balance < 0:
        new_balance = 0

    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
    conn.commit()

    log_action(user_id, "BALANCE_UPDATE", amount, new_balance)
    return new_balance


# ======================
# ADMIN CHECK
# ======================
def is_admin(user_id):
    return user_id in ADMIN_IDS


# ======================
# UI
# ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Games", callback_data="games")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
    ])


def games_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Dice", callback_data="dice")],
        [InlineKeyboardButton("🪙 Coin", callback_data="coin")],
        [InlineKeyboardButton("🎰 Slots", callback_data="slots")],
        [InlineKeyboardButton("⬅️ Back", callback_data="home")],
    ])


# ======================
# START
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id)
    await update.message.reply_text("🎰 Casino Ready", reply_markup=main_menu())


# ======================
# BALANCE
# ======================
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    await update.message.reply_text(f"💰 Balance: {user[1]}")


# ======================
# GAMES (CORE FIX)
# ======================
async def dice_game(update, user_id, bet):
    if get_user(user_id)[1] < bet:
        return await update.message.reply_text("❌ Not enough balance")

    msg = await update.message.reply_dice()
    roll = msg.dice.value

    if roll >= 4:
        win = bet * 2
        new = update_balance(user_id, win)
        await update.message.reply_text(f"🎲 WIN +{win}\n💰 {new}")
    else:
        new = update_balance(user_id, -bet)
        await update.message.reply_text(f"🎲 LOSE -{bet}\n💰 {new}")


async def coin_game(update, user_id, bet):
    if get_user(user_id)[1] < bet:
        return await update.message.reply_text("❌ Not enough balance")

    result = random.choice(["HEAD", "TAIL"])
    win = random.choice(["HEAD", "TAIL"])

    if result == win:
        payout = bet * 2
        new = update_balance(user_id, payout)
        await update.message.reply_text(f"🪙 WIN +{payout}\n💰 {new}")
    else:
        new = update_balance(user_id, -bet)
        await update.message.reply_text(f"🪙 LOSE -{bet}\n💰 {new}")


async def slots_game(update, user_id, bet):
    if get_user(user_id)[1] < bet:
        return await update.message.reply_text("❌ Not enough balance")

    # 🔥 REAL ANIMATION
    msg = await update.message.reply_dice(emoji="🎰")
    value = msg.dice.value

    if value in [1, 22, 43]:
        win = bet * 5
        new = update_balance(user_id, win)
        await update.message.reply_text(f"🎰 JACKPOT +{win}\n💰 {new}")
    else:
        new = update_balance(user_id, -bet)
        await update.message.reply_text(f"🎰 LOSE -{bet}\n💰 {new}")


# ======================
# COMMAND WRAPPERS
# ======================
async def dice(update, context):
    bet = int(context.args[0])
    await dice_game(update, update.effective_user.id, bet)


async def coin(update, context):
    bet = int(context.args[0])
    await coin_game(update, update.effective_user.id, bet)


async def slots(update, context):
    bet = int(context.args[0])
    await slots_game(update, update.effective_user.id, bet)


# ======================
# ADMIN (FIXED)
# ======================
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ No permission")

    await update.message.reply_text("🛠 Admin OK")


# ======================
# CALLBACK MENU
# ======================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    data = q.data

    if data == "home":
        await q.edit_message_text("Main Menu", reply_markup=main_menu())

    elif data == "games":
        await q.edit_message_text("Games", reply_markup=games_menu())

    elif data == "balance":
        user = get_user(user_id)
        await q.edit_message_text(f"💰 {user[1]}")

    elif data in ["dice", "coin", "slots"]:
        await q.edit_message_text("Use command:\n/dice 100")


# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))

    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("slots", slots))

    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()