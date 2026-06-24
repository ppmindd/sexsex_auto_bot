import os
import sqlite3
import random
from datetime import date

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

DB_NAME = "casino.db"

START_POINTS = 500000
CHECKIN_REWARD = 50000
BAILOUT_AMOUNT = 100000


# --------------------
# DB
# --------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        points INTEGER,
        last_checkin TEXT,
        last_bailout TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, username, points, last_checkin, last_bailout FROM users WHERE user_id=?",
        (user_id,)
    )
    user = cur.fetchone()

    conn.close()
    return user


def create_user(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO users
        (user_id, username, points, last_checkin, last_bailout)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            START_POINTS,
            "",
            ""
        )
    )

    conn.commit()
    conn.close()


def update_points(user_id, points):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET points=? WHERE user_id=?",
        (points, user_id)
    )

    conn.commit()
    conn.close()


def update_checkin(user_id, day):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET last_checkin=? WHERE user_id=?",
        (day, user_id)
    )

    conn.commit()
    conn.close()


def update_bailout(user_id, day):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET last_bailout=? WHERE user_id=?",
        (day, user_id)
    )

    conn.commit()
    conn.close()


def update_username(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET username=? WHERE user_id=?",
        (username, user_id)
    )

    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, username, points, last_checkin, last_bailout FROM users WHERE username=?",
        (username,)
    )

    user = cur.fetchone()

    conn.close()
    return user


# --------------------
# Helpers
# --------------------
def ensure_user(update: Update):
    tg_user = update.effective_user

    user = get_user(tg_user.id)

    if not user:
        create_user(
            tg_user.id,
            tg_user.username or ""
        )
    else:
        update_username(
            tg_user.id,
            tg_user.username or ""
        )


# --------------------
# Commands
# --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)

    await update.message.reply_text(
        f"🎰 마닐라 카지노\n\n"
        f"초기 지급금: {START_POINTS:,} 칩\n\n"
        f"명령어:\n"
        f"/출석\n"
        f"/잔액\n"
        f"/주사위 금액\n"
        f"/홀짝 금액 홀|짝\n"
        f"/송금 @유저 금액\n"
        f"/구제"
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)

    user = get_user(update.effective_user.id)

    await update.message.reply_text(
        f"💰 현재 잔액: {user[2]:,} 칩"
    )


async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)

    today = str(date.today())

    user = get_user(update.effective_user.id)

    if user[3] == today:
        await update.message.reply_text(
            "❌ 오늘은 이미 출석했습니다."
        )
        return

    new_points = user[2] + CHECKIN_REWARD

    update_points(user[0], new_points)
    update_checkin(user[0], today)

    await update.message.reply_text(
        f"✅ 출석 완료!\n+{CHECKIN_REWARD:,} 칩\n\n"
        f"현재 잔액: {new_points:,}"
    )


async def bailout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)

    today = str(date.today())
    user = get_user(update.effective_user.id)

    if user[2] > 0:
        await update.message.reply_text(
            "❌ 잔액이 0일 때만 구제 가능합니다."
        )
        return

    if user[4] == today:
        await update.message.reply_text(
            "❌ 오늘은 이미 구제를 받았습니다."
        )
        return

    update_points(user[0], BAILOUT_AMOUNT)
    update_bailout(user[0], today)

    await update.message.reply_text(
        f"🆘 구제금 지급!\n"
        f"+{BAILOUT_AMOUNT:,} 칩"
    )


async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)

    if len(context.args) != 1:
        await update.message.reply_text(
            "사용법: /주사위 금액"
        )
        return

    try:
        bet = int(context.args[0])
    except:
        await update.message.reply_text("금액 오류")
        return

    user = get_user(update.effective_user.id)

    if bet <= 0:
        await update.message.reply_text("금액 오류")
        return

    if user[2] < bet:
        await update.message.reply_text("잔액 부족")
        return

    roll = random.randint(1, 6)

    points = user[2]

    if roll >= 4:
        points += bet
        result = f"🎲 {roll}\n승리!\n+{bet:,}"
    else:
        points -= bet
        result = f"🎲 {roll}\n패배!\n-{bet:,}"

    update_points(user[0], points)

    await update.message.reply_text(
        f"{result}\n\n잔액: {points:,}"
    )


async def odd_even(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)

    if len(context.args) != 2:
        await update.message.reply_text(
            "사용법: /홀짝 금액 홀"
        )
        return

    try:
        bet = int(context.args[0])
    except:
        await update.message.reply_text("금액 오류")
        return

    choice = context.args[1]

    if choice not in ["홀", "짝"]:
        await update.message.reply_text(
            "홀 또는 짝 입력"
        )
        return

    user = get_user(update.effective_user.id)

    if user[2] < bet:
        await update.message.reply_text("잔액 부족")
        return

    num = random.randint(1, 10)

    result_side = "홀" if num % 2 else "짝"

    points = user[2]

    if choice == result_side:
        points += bet
        msg = f"🎯 결과: {num} ({result_side})\n승리!\n+{bet:,}"
    else:
        points -= bet
        msg = f"🎯 결과: {num} ({result_side})\n패배!\n-{bet:,}"

    update_points(user[0], points)

    await update.message.reply_text(
        f"{msg}\n\n잔액: {points:,}"
    )


async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update)

    if len(context.args) != 2:
        await update.message.reply_text(
            "사용법: /송금 @유저 금액"
        )
        return

    username = context.args[0].replace("@", "")

    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("금액 오류")
        return

    sender = get_user(update.effective_user.id)

    target = get_user_by_username(username)

    if not target:
        await update.message.reply_text(
            "대상 유저가 없습니다.\n대상이 먼저 /start 해야 합니다."
        )
        return

    if amount <= 0:
        await update.message.reply_text("금액 오류")
        return

    if sender[2] < amount:
        await update.message.reply_text("잔액 부족")
        return

    update_points(
        sender[0],
        sender[2] - amount
    )

    update_points(
        target[0],
        target[2] + amount
    )

    await update.message.reply_text(
        f"✅ @{username} 에게 {amount:,} 칩 송금 완료"
    )


def main():
    init_db()

    token = os.getenv("BOT_TOKEN")

    if not token:
        raise ValueError("BOT_TOKEN not found")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("checkin", checkin))
app.add_handler(CommandHandler("balance", balance))
app.add_handler(CommandHandler("dice", dice))
app.add_handler(CommandHandler("oddeven", odd_even))
app.add_handler(CommandHandler("pay", transfer))
app.add_handler(CommandHandler("bailout", bailout))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()