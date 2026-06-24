import os
import sqlite3
import random
from datetime import date

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

DB = "casino.db"

START_BALANCE = 500000
DAILY_REWARD = 50000
RELIEF_AMOUNT = 100000


# ---------------- DB ----------------
def db():
    return sqlite3.connect(DB)


def init():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        last_checkin TEXT,
        last_relief TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_user(uid):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    return row


def create_user(uid, username):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, ?)",
        (uid, username, START_BALANCE)
    )
    conn.commit()
    conn.close()


def update_balance(uid, amount):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()
    conn.close()


def update_checkin(uid):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (str(date.today()), uid))
    conn.commit()
    conn.close()


def update_relief(uid):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_relief=? WHERE user_id=?", (str(date.today()), uid))
    conn.commit()
    conn.close()


# ---------------- HELPERS ----------------
def ensure(uid, username):
    if not get_user(uid):
        create_user(uid, username)


def balance(uid):
    row = get_user(uid)
    return row[2] if row else 0


# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure(u.id, u.username)

    await update.message.reply_text(
        f"🎰 Casino Bot\n"
        f"Welcome!\n"
        f"+{START_BALANCE:,} coins added"
    )


async def bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure(u.id, u.username)

    await update.message.reply_text(f"💰 Balance: {balance(u.id):,}")


async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure(u.id, u.username)

    row = get_user(u.id)
    today = str(date.today())

    if row[3] == today:
        await update.message.reply_text("Already checked in today.")
        return

    update_balance(u.id, DAILY_REWARD)
    update_checkin(u.id)

    await update.message.reply_text(f"Check-in done!\n+{DAILY_REWARD:,}")


async def relief(update, context):
    user_id = update.effective_user.id
    user = get_user(user_id)
    balance = user[1]

    if balance > 0:
        await update.message.reply_text("❌ Relief is only available when your balance is 0.")
        return

    amount = 500_000

    update_balance(user_id, amount)

    await update.message.reply_text(f"🆘 Relief activated! +{amount:,}")


async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure(u.id, u.username)

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /dice 50000")
        return

    bet = int(context.args[0])

    if balance(u.id) < bet:
        await update.message.reply_text("Not enough balance.")
        return

    roll = random.randint(1, 6)

    if roll >= 4:
        update_balance(u.id, bet)
        await update.message.reply_text(f"🎲 {roll}\nWIN +{bet:,}")
    else:
        update_balance(u.id, -bet)
        await update.message.reply_text(f"🎲 {roll}\nLOSE -{bet:,}")


async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure(u.id, u.username)

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /coin 50000 head|tail")
        return

    bet = int(context.args[0])
    choice = context.args[1].lower()

    if choice not in ["head", "tail"]:
        await update.message.reply_text("Choose head or tail")
        return

    if balance(u.id) < bet:
        await update.message.reply_text("Not enough balance.")
        return

    result = random.choice(["head", "tail"])

    if result == choice:
        update_balance(u.id, bet)
        await update.message.reply_text(f"Result: {result}\nWIN +{bet:,}")
    else:
        update_balance(u.id, -bet)
        await update.message.reply_text(f"Result: {result}\nLOSE -{bet:,}")


async def send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure(u.id, u.username)

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user message to send coins.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: reply + /send 50000")
        return

    amount = int(context.args[0])
    target = update.message.reply_to_message.from_user

    ensure(target.id, target.username)

    if balance(u.id) < amount:
        await update.message.reply_text("Not enough balance.")
        return

    update_balance(u.id, -amount)
    update_balance(target.id, amount)

    await update.message.reply_text(f"Sent {amount:,} coins")

import random

def baccarat_score():
    cards = [random.randint(1, 10) for _ in range(3)]
    return sum(cards) % 10, cards


async def baccarat(update, context):
    user_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /baccarat <bet> player|banker|tie")
        return

    try:
        bet = int(context.args[0])
    except:
        await update.message.reply_text("Bet must be a number")
        return

    choice = context.args[1].lower()

    user = get_user(user_id)
    if not user:
        await update.message.reply_text("User not registered. Use /start")
        return

    balance = user[2]

    if bet <= 0:
        await update.message.reply_text("Bet must be > 0")
        return

    if bet > balance:
        await update.message.reply_text("Not enough balance")
        return

    if choice not in ["player", "banker", "tie"]:
        await update.message.reply_text("Choose: player / banker / tie")
        return

    p_score, p_cards = baccarat_score()
    b_score, b_cards = baccarat_score()

    if p_score > b_score:
        result = "player"
    elif b_score > p_score:
        result = "banker"
    else:
        result = "tie"

    if choice == result:
        change = bet * 8 if result == "tie" else bet
        msg = "YOU WIN"
    else:
        change = -bet
        msg = "YOU LOSE"

    update_balance(user_id, change)

    await update.message.reply_text(
    f"🃏 BACCARAT\n\n"
    f"You: {choice}\n\n"
    f"Player: {p_cards} → {p_score}\n"
    f"Banker: {b_cards} → {b_score}\n\n"
    f"Result: {result}\n"
    f"{msg}\n"
    f"Change: {change:+}"
)
import random

symbols = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]


def slot_spin():
    return [random.choice(symbols) for _ in range(3)]


async def slot(update, context):
    user_id = update.effective_user.id

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /slot <bet>")
        return

    try:
        bet = int(context.args[0])
    except:
        await update.message.reply_text("Bet must be a number")
        return

    user = get_user(user_id)
    if not user:
        await update.message.reply_text("User not registered. Use /start")
        return

    balance = user[2]

    if bet <= 0 or bet > balance:
        await update.message.reply_text("Invalid bet amount")
        return

    reels = slot_spin()

    if reels[0] == reels[1] == reels[2]:
        if reels[0] == "7️⃣":
            multiplier = 10
        elif reels[0] == "💎":
            multiplier = 7
        else:
            multiplier = 5

        change = bet * multiplier
        result = "JACKPOT"
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        change = bet * 2
        result = "SMALL WIN"
    else:
        change = -bet
        result = "LOSE"

    update_balance(user_id, change)

    await update.message.reply_text(
        f"🎰 SLOT MACHINE\n\n"
        f"| {' | '.join(reels)} |\n\n"
        f"{result}\n"
        f"Change: {change:+}"
    )

# ---------------- MAIN ----------------
def main():
    init()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", bal))
    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("relief", relief))
    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("send", send))
    app.add_handler(CommandHandler("baccarat", baccarat))
    app.add_handler(CommandHandler("slot", slot))
    app.run_polling()
    
    

if __name__ == "__main__":
    main()