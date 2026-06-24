import os
import sqlite3
import random
import logging
import asyncio
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {7381851504}

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
def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    u = cur.fetchone()

    if not u:
        cur.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (uid, 1000000)
        )
        conn.commit()
        return (uid, 1000000, None)

    return u


def log(uid, action, amount, balance):
    cur.execute(
        "INSERT INTO logs VALUES (NULL,?,?,?,?,?)",
        (uid, action, amount, balance, datetime.now().isoformat())
    )
    conn.commit()


def update_balance(uid, amount):
    u = get_user(uid)
    new = u[1] + amount

    if new < 0:
        new = 0

    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new, uid))
    conn.commit()

    log(uid, "BAL", amount, new)
    return new


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


def games_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Dice", callback_data="dice")],
        [InlineKeyboardButton("🪙 Coin", callback_data="coin")],
        [InlineKeyboardButton("🎰 Slots", callback_data="slots")],
        [InlineKeyboardButton("🃏 Baccarat", callback_data="baccarat")],
        [InlineKeyboardButton("⬅️ Back", callback_data="home")],
    ])


# ======================
# START / BALANCE
# ======================
async def start(update, context):
    get_user(update.effective_user.id)
    await update.message.reply_text("🎰 Casino Pro Ready", reply_markup=menu())


async def balance(update, context):
    u = get_user(update.effective_user.id)
    await update.message.reply_text(f"💰 {u[1]}")


# ======================
# CHECKIN / RELIEF
# ======================
async def checkin(update, context):
    uid = update.effective_user.id
    u = get_user(uid)

    today = date.today().isoformat()

    if u[2] == today:
        return await update.message.reply_text("Already claimed")

    reward = random.randint(1000000, 3000000)
    new = update_balance(uid, reward)

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (today, uid))
    conn.commit()

    await update.message.reply_text(f"🎁 +{reward}\n💰 {new}")


async def relief(update, context):
    uid = update.effective_user.id
    u = get_user(uid)

    if u[1] > 0:
        return await update.message.reply_text("Only for zero balance")

    new = update_balance(uid, 500000)
    await update.message.reply_text(f"🆘 +500000\n💰 {new}")


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

        if get_user(uid)[1] < amt:
            return await update.message.reply_text("No balance")

        update_balance(uid, -amt)
        update_balance(target, amt)

        await update.message.reply_text("Transferred")

    except:
        await update.message.reply_text("/transfer <id> <amount>")


# ======================
# ADMIN
# ======================
async def admin(update, context):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("No permission")

    await update.message.reply_text("🛠 Admin Ready")


async def addmoney(update, context):
    if not is_admin(update.effective_user.id):
        return

    uid = int(context.args[0])
    amt = int(context.args[1])

    new = update_balance(uid, amt)
    await update.message.reply_text(f"➕ +{amt}\n💰 {new}")


async def removemoney(update, context):
    if not is_admin(update.effective_user.id):
        return

    uid = int(context.args[0])
    amt = int(context.args[1])

    new = update_balance(uid, -amt)
    await update.message.reply_text(f"➖ -{amt}\n💰 {new}")


# ======================
# GAMES
# ======================
def check(uid, bet):
    return get_user(uid)[1] >= bet


async def dice_game(update, uid, bet):
    msg = await update.message.reply_dice()
    v = msg.dice.value

    if v >= 4:
        new = update_balance(uid, bet * 2)
        await update.message.reply_text(f"🎲 WIN +{bet*2}\n💰 {new}")
    else:
        new = update_balance(uid, -bet)
        await update.message.reply_text(f"🎲 LOSE -{bet}\n💰 {new}")


async def coin_game(update, uid, bet):
    msg = await update.message.reply_dice("🪙")

    if msg.dice.value % 2 == 0:
        new = update_balance(uid, bet * 2)
        await update.message.reply_text(f"🪙 WIN +{bet*2}")
    else:
        new = update_balance(uid, -bet)
        await update.message.reply_text(f"🪙 LOSE -{bet}")


async def slots_game(update, uid, bet):
    msg = await update.message.reply_dice("🎰")

    if msg.dice.value in [1, 22, 43]:
        new = update_balance(uid, bet * 5)
        await update.message.reply_text(f"🎰 JACKPOT +{bet*5}")
    else:
        new = update_balance(uid, -bet)
        await update.message.reply_text(f"🎰 LOSE -{bet}")


# ======================
# 🃏 BACCARAT (ANIMATION VERSION)
# ======================
async def baccarat_game(update, uid, bet):
    msg = await update.message.reply_text("🃏 Dealing cards...")

    await asyncio.sleep(1)
    await msg.edit_text("🃏 Player: ♦️🂠 | Banker: ♠️🂠")

    await asyncio.sleep(1)

    p = random.randint(1, 9)
    b = random.randint(1, 9)

    text = f"🃏 Player: {p} | Banker: {b}\n"

    if p > b:
        new = update_balance(uid, bet)
        text += f"🎉 Player Win +{bet}"
    elif b > p:
        new = update_balance(uid, -bet)
        text += f"💥 Banker Win -{bet}"
    else:
        new = get_user(uid)[1]
        text += "🤝 Tie"

    text += f"\n💰 {new}"

    await msg.edit_text(text)


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
        await q.edit_message_text("Games", reply_markup=games_menu())

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
    app.add_handler(CommandHandler("addmoney", addmoney))
    app.add_handler(CommandHandler("removemoney", removemoney))

    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("slots", slots))
    app.add_handler(CommandHandler("baccarat", baccarat))

    app.add_handler(CallbackQueryHandler(button))

    print("🔥 Casino Pro Running...")
    app.run_polling()


if __name__ == "__main__":
    main()