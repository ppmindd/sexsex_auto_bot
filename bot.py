import os
import asyncio
import random
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ===================== 설정 =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {7381851504}

INITIAL_BALANCE = 1_000_000
CHECKIN_MIN = 1_000_000
CHECKIN_MAX = 3_000_000
RELIEF_AMOUNT = 500_000

DB_PATH = "casino.db"

# ===================== DB =====================
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
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
    time TEXT
)
""")

conn.commit()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_user(user_id):
    cur.execute("SELECT user_id, balance, last_checkin FROM users WHERE user_id=?", (user_id,))
    return cur.fetchone()


def create_user(user_id):
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)",
        (user_id, INITIAL_BALANCE),
    )
    conn.commit()


def update_balance(user_id, amount, action=""):
    create_user(user_id)
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = cur.fetchone()[0]
    new_bal = bal + amount

    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, user_id))
    conn.commit()

    cur.execute(
        "INSERT INTO logs (user_id, action, amount, balance, time) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, amount, new_bal, now()),
    )
    conn.commit()

    return new_bal


def set_checkin(user_id):
    cur.execute(
        "UPDATE users SET last_checkin=? WHERE user_id=?",
        (now(), user_id),
    )
    conn.commit()


# ===================== UI =====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 게임", callback_data="menu_games")],
        [InlineKeyboardButton("💰 잔액", callback_data="menu_balance")],
        [InlineKeyboardButton("🎁 출석체크", callback_data="menu_checkin")],
        [InlineKeyboardButton("🆘 구제", callback_data="menu_relief")],
    ])


def game_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 주사위", callback_data="game_dice")],
        [InlineKeyboardButton("🪙 동전", callback_data="game_coin")],
        [InlineKeyboardButton("🎰 슬롯", callback_data="game_slots")],
        [InlineKeyboardButton("🃏 바카라", callback_data="game_baccarat")],
        [InlineKeyboardButton("⬅ 뒤로", callback_data="menu_back")],
    ])


# ===================== 기본 명령 =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user(user_id)

    await update.message.reply_text(
        "🎰 카지노 봇에 오신 것을 환영합니다!",
        reply_markup=main_menu()
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user(user_id)

    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = cur.fetchone()[0]

    await update.message.reply_text(f"💰 현재 잔액: {bal:,} 코인")


async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target = int(context.args[0])
        amount = int(context.args[1])
        user_id = update.effective_user.id

        if amount <= 0:
            return await update.message.reply_text("❌ 금액 오류")

        cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        bal = cur.fetchone()[0]

        if bal < amount:
            return await update.message.reply_text("❌ 잔액 부족")

        update_balance(user_id, -amount, "transfer_out")
        update_balance(target, amount, "transfer_in")

        await update.message.reply_text("✅ 송금 완료")

    except:
        await update.message.reply_text("사용법: /transfer <유저ID> <금액>")


async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user(user_id)

    cur.execute("SELECT last_checkin FROM users WHERE user_id=?", (user_id,))
    last = cur.fetchone()[0]

    if last and last[:10] == now()[:10]:
        return await update.message.reply_text("❌ 오늘은 이미 출석했습니다")

    reward = random.randint(CHECKIN_MIN, CHECKIN_MAX)
    update_balance(user_id, reward, "checkin")
    set_checkin(user_id)

    await update.message.reply_text(f"🎁 출석 보상: +{reward:,}")


async def relief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user(user_id)

    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = cur.fetchone()[0]

    if bal != 0:
        return await update.message.reply_text("❌ 잔액이 0일 때만 가능합니다")

    update_balance(user_id, RELIEF_AMOUNT, "relief")

    await update.message.reply_text(f"🆘 구제 지급: +{RELIEF_AMOUNT:,}")


# ===================== 게임 =====================
async def dice_game(update, user_id):
    msg = await update.message.reply_text("🎲 굴리는 중...")
    res = await update.effective_chat.send_dice("🎲")
    await asyncio.sleep(2)

    await msg.edit_text(f"결과: {res.dice.value}")


async def coin_game(update, user_id):
    msg = await update.message.reply_text("🪙 던지는 중...")
    res = await update.effective_chat.send_dice("🎲")
    await asyncio.sleep(2)

    result = "앞면" if res.dice.value % 2 == 0 else "뒷면"
    await msg.edit_text(f"결과: {result}")


async def slots_game(update, user_id):
    msg = await update.message.reply_text("🎰 스핀 중...")
    res = await update.effective_chat.send_dice("🎰")
    await asyncio.sleep(3)

    await msg.edit_text(f"슬롯 결과: {res.dice.value}")


async def baccarat_game(update, user_id):
    msg = await update.message.reply_text("🃏 카드 배분 중...")

    player = random.randint(1, 10)
    banker = random.randint(1, 10)

    await asyncio.sleep(1)
    await msg.edit_text(f"플레이어: {player}")
    await asyncio.sleep(1)
    await msg.edit_text(f"뱅커: {banker}")

    if player > banker:
        result = "플레이어 승"
    elif banker > player:
        result = "뱅커 승"
    else:
        result = "무승부"

    await asyncio.sleep(1)
    await msg.edit_text(f"결과: {result}")


# ===================== 콜백 =====================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    create_user(user_id)

    data = query.data

    if data == "menu_games":
        await query.message.edit_text("🎮 게임 선택", reply_markup=game_menu())

    elif data == "menu_balance":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        bal = cur.fetchone()[0]
        await query.message.edit_text(f"💰 잔액: {bal:,}", reply_markup=main_menu())

    elif data == "menu_checkin":
        await checkin(update, context)

    elif data == "menu_relief":
        await relief(update, context)

    elif data == "menu_back":
        await query.message.edit_text("🏠 메인 메뉴", reply_markup=main_menu())

    elif data == "game_dice":
        await dice_game(update, user_id)

    elif data == "game_coin":
        await coin_game(update, user_id)

    elif data == "game_slots":
        await slots_game(update, user_id)

    elif data == "game_baccarat":
        await baccarat_game(update, user_id)


# ===================== 관리자 =====================
async def addmoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])
    amount = int(context.args[1])

    update_balance(uid, amount, "admin_add")
    await update.message.reply_text("관리자 지급 완료")


async def removemoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])
    amount = -abs(int(context.args[1]))

    update_balance(uid, amount, "admin_remove")
    await update.message.reply_text("관리자 차감 완료")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()

    text = "\n".join([str(r) for r in rows])
    await update.message.reply_text(text)


async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()

    text = "🏆 랭킹\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r[0]} - {r[1]:,}\n"

    await update.message.reply_text(text)


# ===================== 실행 =====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("transfer", transfer))
    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("relief", relief))

    app.add_handler(CommandHandler("addmoney", addmoney))
    app.add_handler(CommandHandler("removemoney", removemoney))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("rank", rank))

    app.add_handler(CallbackQueryHandler(button))

    print("봇 실행 중...")
    app.run_polling()


if __name__ == "__main__":
    main()