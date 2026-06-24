import os
import sqlite3
import random
import logging
from datetime import datetime, date

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
ADMIN_IDS = {123456789}  # 본인 Telegram ID로 변경

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ======================
# DB SETUP
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
        cur.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 1000))
        conn.commit()
        return (user_id, 1000, None)
    return row


def update_balance(user_id, amount):
    user = get_user(user_id)
    new_balance = user[1] + amount
    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
    conn.commit()
    log_action(user_id, "BALANCE_UPDATE", amount, new_balance)
    return new_balance


def set_balance(user_id, amount):
    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (amount, user_id))
    conn.commit()
    log_action(user_id, "SET_BALANCE", amount, amount)


def log_action(user_id, action, amount, balance):
    cur.execute(
        "INSERT INTO logs (user_id, action, amount, balance, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, amount, balance, datetime.now().isoformat()),
    )
    conn.commit()


# ======================
# UI
# ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Games", callback_data="games")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("🎁 Checkin", callback_data="checkin")],
        [InlineKeyboardButton("🆘 Relief", callback_data="relief")],
    ])


def games_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Dice", callback_data="dice")],
        [InlineKeyboardButton("🪙 Coin Flip", callback_data="coin")],
        [InlineKeyboardButton("🎰 Slots", callback_data="slots")],
        [InlineKeyboardButton("🃏 Baccarat", callback_data="baccarat")],
        [InlineKeyboardButton("⬅️ Back", callback_data="home")],
    ])


# ======================
# COMMANDS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    get_user(user_id)

    await update.message.reply_text(
        "🎰 Welcome to Casino Bot!",
        reply_markup=main_menu()
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    await update.message.reply_text(f"💰 Balance: {user[1]}")


async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        target = int(context.args[0])
        amount = int(context.args[1])

        if amount <= 0:
            return await update.message.reply_text("Invalid amount")

        sender = get_user(user_id)
        if sender[1] < amount:
            return await update.message.reply_text("Not enough balance")

        update_balance(user_id, -amount)
        update_balance(target, amount)

        await update.message.reply_text("Transfer successful")

    except:
        await update.message.reply_text("Usage: /transfer <user_id> <amount>")


async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    today = date.today().isoformat()

    if user[2] == today:
        return await update.message.reply_text("Already checked in today")

    reward = random.randint(100, 500)
    new_balance = update_balance(user_id, reward)

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (today, user_id))
    conn.commit()

    await update.message.reply_text(f"🎁 +{reward} claimed! Balance: {new_balance}")


async def relief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user[1] > 0:
        return await update.message.reply_text("Relief only for zero balance")

    reward = 500
    new_balance = update_balance(user_id, reward)

    await update.message.reply_text(f"🆘 Relief granted: {new_balance}")


# ======================
# ADMIN
# ======================
def is_admin(user_id):
    return user_id in ADMIN_IDS


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("No permission")

    await update.message.reply_text(
        "Admin Panel",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Money", callback_data="addmoney")],
            [InlineKeyboardButton("➖ Remove Money", callback_data="removemoney")],
            [InlineKeyboardButton("📜 Logs", callback_data="logs")],
            [InlineKeyboardButton("🏆 Rank", callback_data="rank")],
        ])
    )


async def addmoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
        new = update_balance(uid, amt)
        await update.message.reply_text(f"Added. New balance: {new}")
    except:
        await update.message.reply_text("Usage: /addmoney <user_id> <amount>")


async def removemoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
        new = update_balance(uid, -amt)
        await update.message.reply_text(f"Removed. New balance: {new}")
    except:
        await update.message.reply_text("Usage: /removemoney <user_id> <amount>")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()

    text = "\n".join([str(r) for r in rows])
    await update.message.reply_text(text or "No logs")


async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()

    msg = "\n".join([f"{u}: {b}" for u, b in rows])
    await update.message.reply_text(msg)


# ======================
# GAMES
# ======================
def bet_check(user_id, bet):
    user = get_user(user_id)
    return user[1] >= bet


async def dice_game(update, user_id, bet):
    if not bet_check(user_id, bet):
        return await update.message.reply_text("Not enough balance")

    roll = random.randint(1, 6)

    if roll >= 4:
        win = bet * 2
        update_balance(user_id, win)
        result = f"You win {win}"
    else:
        update_balance(user_id, -bet)
        result = "You lose"

    await update.message.reply_text(f"🎲 {roll}\n{result}")


async def coin_game(update, user_id, bet):
    if not bet_check(user_id, bet):
        return await update.message.reply_text("Not enough balance")

    result = random.choice(["HEAD", "TAIL"])
    win = random.choice(["HEAD", "TAIL"])

    if result == win:
        payout = bet * 2
        update_balance(user_id, payout)
        msg = "You win"
    else:
        update_balance(user_id, -bet)
        msg = "You lose"

    await update.message.reply_text(f"🪙 {result} vs {win}\n{msg}")


async def slots_game(update, user_id, bet):
    if not bet_check(user_id, bet):
        return await update.message.reply_text("Not enough balance")

    symbols = ["🍒", "🍋", "🔔", "⭐"]
    spin = [random.choice(symbols) for _ in range(3)]

    if spin.count(spin[0]) == 3:
        win = bet * 5
        update_balance(user_id, win)
        msg = "JACKPOT!"
    else:
        update_balance(user_id, -bet)
        msg = "Lose"

    await update.message.reply_text(f"{spin}\n{msg}")


async def baccarat_game(update, user_id, bet):
    if not bet_check(user_id, bet):
        return await update.message.reply_text("Not enough balance")

    player = random.randint(1, 9)
    banker = random.randint(1, 9)

    if player > banker:
        update_balance(user_id, bet)
        result = "Player wins"
    elif banker > player:
        update_balance(user_id, -bet)
        result = "Banker wins"
    else:
        result = "Tie"

    await update.message.reply_text(f"P:{player} B:{banker}\n{result}")


# ======================
# CALLBACKS
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
        await q.edit_message_text(f"Balance: {user[1]}")

    elif data == "checkin":
        today = date.today().isoformat()
        user = get_user(user_id)

        if user[2] == today:
            return await q.edit_message_text("Already claimed")

        reward = random.randint(100, 500)
        new = update_balance(user_id, reward)

        cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (today, user_id))
        conn.commit()

        await q.edit_message_text(f"+{reward} claimed\nBalance: {new}")

    elif data == "relief":
        user = get_user(user_id)

        if user[1] > 0:
            return await q.edit_message_text("Not eligible")

        new = update_balance(user_id, 500)
        await q.edit_message_text(f"Relief: {new}")

    elif data in ["dice", "coin", "slots", "baccarat"]:
        await q.edit_message_text("Send bet like:\n/dice 100")


# ======================
# GAME COMMAND WRAPPER
# ======================
async def dice(update, context):
    user_id = update.effective_user.id
    bet = int(context.args[0])
    await dice_game(update, user_id, bet)


async def coin(update, context):
    user_id = update.effective_user.id
    bet = int(context.args[0])
    await coin_game(update, user_id, bet)


async def slots(update, context):
    user_id = update.effective_user.id
    bet = int(context.args[0])
    await slots_game(update, user_id, bet)


async def baccarat(update, context):
    user_id = update.effective_user.id
    bet = int(context.args[0])
    await baccarat_game(update, user_id, bet)


# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("transfer", transfer))
    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("relief", relief))

    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addmoney", addmoney))
    app.add_handler(CommandHandler("removemoney", removemoney))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("rank", rank))

    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("slots", slots))
    app.add_handler(CommandHandler("baccarat", baccarat))

    app.add_handler(CallbackQueryHandler(button))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()