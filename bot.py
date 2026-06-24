import os
import sqlite3
import random
import logging
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {7381851504}  # 👈 반드시 수정

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
# DB CORE
# ======================
def get_user(user_id):
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, 1000000)  # 초기 자본
        )
        conn.commit()
        return (user_id, 1000000, None)

    return row


def log(user_id, action, amount, balance):
    cur.execute(
        "INSERT INTO logs (user_id, action, amount, balance, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, amount, balance, datetime.now().isoformat())
    )
    conn.commit()


def update_balance(user_id, amount):
    u = get_user(user_id)
    new = u[1] + amount

    if new < 0:
        new = 0

    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new, user_id))
    conn.commit()

    log(user_id, "BALANCE", amount, new)
    return new


# ======================
# CHECK ADMIN
# ======================
def is_admin(uid):
    return uid in ADMIN_IDS


# ======================
# UI
# ======================
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Games", callback_data="games")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("🎁 Checkin", callback_data="checkin")],
        [InlineKeyboardButton("🆘 Relief", callback_data="relief")],
    ])


def games():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Dice", callback_data="dice")],
        [InlineKeyboardButton("🪙 Coin", callback_data="coin")],
        [InlineKeyboardButton("🎰 Slots", callback_data="slots")],
        [InlineKeyboardButton("🃏 Baccarat", callback_data="baccarat")],
        [InlineKeyboardButton("⬅️ Back", callback_data="home")],
    ])


# ======================
# START
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id)
    await update.message.reply_text("🎰 Casino Bot Ready", reply_markup=menu())


# ======================
# BALANCE
# ======================
async def balance(update, context):
    u = get_user(update.effective_user.id)
    await update.message.reply_text(f"💰 {u[1]}")


# ======================
# CHECKIN
# ======================
async def checkin(update, context):
    uid = update.effective_user.id
    u = get_user(uid)

    today = date.today().isoformat()

    if u[2] == today:
        return await update.message.reply_text("Already claimed")

    reward = random.randint(500000, 2000000)
    new = update_balance(uid, reward)

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (today, uid))
    conn.commit()

    await update.message.reply_text(f"🎁 +{reward}\n💰 {new}")


# ======================
# RELIEF
# ======================
async def relief(update, context):
    uid = update.effective_user.id
    u = get_user(uid)

    if u[1] > 0:
        return await update.message.reply_text("Only for zero balance")

    new = update_balance(uid, 1000000)
    await update.message.reply_text(f"🆘 +1000000\n💰 {new}")


# ======================
# TRANSFER
# ======================
async def transfer(update, context):
    try:
        uid = update.effective_user.id
        target = int(context.args[0])
        amt = int(context.args[1])

        if amt <= 0:
            return await update.message.reply_text("Invalid")

        u = get_user(uid)

        if u[1] < amt:
            return await update.message.reply_text("No balance")

        update_balance(uid, -amt)
        update_balance(target, amt)

        await update.message.reply_text("Sent")

    except:
        await update.message.reply_text("/transfer <id> <amount>")


# ======================
# ADMIN PANEL
# ======================
async def admin(update, context):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("No permission")

    await update.message.reply_text(
        "ADMIN",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Logs", callback_data="logs")],
            [InlineKeyboardButton("Rank", callback_data="rank")],
        ])
    )


async def logs(update, context):
    if not is_admin(update.effective_user.id):
        return

    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()

    await update.message.reply_text("\n".join(map(str, rows)))


async def rank(update, context):
    if not is_admin(update.effective_user.id):
        return

    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()

    await update.message.reply_text("\n".join([f"{a}:{b}" for a, b in rows]))
    
    
# ======================
# GAMES CORE
# ======================
def check(uid, bet):
    return get_user(uid)[1] >= bet


async def dice_game(update, uid, bet):
    if not check(uid, bet):
        return await update.message.reply_text("No balance")

    msg = await update.message.reply_dice()
    v = msg.dice.value

    if v >= 4:
        win = bet * 2
        new = update_balance(uid, win)
        await update.message.reply_text(f"WIN +{win}\n💰{new}")
    else:
        new = update_balance(uid, -bet)
        await update.message.reply_text(f"LOSE -{bet}\n💰{new}")


async def coin_game(update, uid, bet):
    if not check(uid, bet):
        return await update.message.reply_text("No balance")

    a = random.choice(["H", "T"])
    b = random.choice(["H", "T"])

    if a == b:
        new = update_balance(uid, bet * 2)
        await update.message.reply_text(f"WIN 💰{new}")
    else:
        new = update_balance(uid, -bet)
        await update.message.reply_text(f"LOSE 💰{new}")


async def slots_game(update, uid, bet):
    if not check(uid, bet):
        return await update.message.reply_text("No balance")

    msg = await update.message.reply_dice(emoji="🎰")
    v = msg.dice.value

    if v in [1, 22, 43]:
        new = update_balance(uid, bet * 5)
        await update.message.reply_text(f"JACKPOT 💰{new}")
    else:
        new = update_balance(uid, -bet)
        await update.message.reply_text(f"LOSE 💰{new}")


async def baccarat_game(update, uid, bet):
    if not check(uid, bet):
        return await update.message.reply_text("No balance")

    p = random.randint(1, 9)
    b = random.randint(1, 9)

    if p > b:
        new = update_balance(uid, bet)
    elif b > p:
        new = update_balance(uid, -bet)
    else:
        new = get_user(uid)[1]

    await update.message.reply_text(f"P:{p} B:{b}\n💰{new}")


# ======================
# CALLBACK
# ======================
async def button(update, context):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    d = q.data

    if d == "home":
        await q.edit_message_text("Menu", reply_markup=menu())

    elif d == "games":
        await q.edit_message_text("Games", reply_markup=games())

    elif d == "balance":
        u = get_user(uid)
        await q.edit_message_text(f"💰 {u[1]}")

    elif d == "checkin":
        await checkin(update, context)

    elif d == "relief":
        await relief(update, context)

    elif d in ["dice", "coin", "slots", "baccarat"]:
        await q.edit_message_text("Use /command bet")


# ======================
# WRAPPERS
# ======================
async def dice(update, context):
    await dice_game(update, update.effective_user.id, int(context.args[0]))


async def coin(update, context):
    await coin_game(update, update.effective_user.id, int(context.args[0]))


async def slots(update, context):
    await slots_game(update, update.effective_user.id, int(context.args[0]))


async def baccarat(update, context):
    await baccarat_game(update, update.effective_user.id, int(context.args[0]))


# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))

    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("relief", relief))
    app.add_handler(CommandHandler("transfer", transfer))

    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("rank", rank))

    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("slots", slots))
    app.add_handler(CommandHandler("baccarat", baccarat))

    app.add_handler(CallbackQueryHandler(button))
    
    
    print("RUNNING")
    app.run_polling()


if __name__ == "__main__":
    main()