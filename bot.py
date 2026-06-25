import os
import asyncio
import random
import sqlite3
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= 설정 =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {7381851504}

INITIAL_BALANCE = 1_000_000
CHECKIN_MIN = 1_000_000
CHECKIN_MAX = 3_000_000
RELIEF_AMOUNT = 500_000

conn = sqlite3.connect("casino.db", check_same_thread=False)
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


def create_user(uid):
    cur.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (uid, INITIAL_BALANCE))
    conn.commit()


def get_balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()[0]


def update_balance(uid, amount, action=""):
    create_user(uid)
    bal = get_balance(uid)
    new_bal = bal + amount

    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, uid))
    conn.commit()

    cur.execute(
        "INSERT INTO logs (user_id, action, amount, balance, time) VALUES (?, ?, ?, ?, ?)",
        (uid, action, amount, new_bal, now()),
    )
    conn.commit()

    return new_bal


# ================= UI =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 게임", callback_data="게임")],
        [InlineKeyboardButton("💰 잔액", callback_data="잔액")],
        [InlineKeyboardButton("🎁 출석", callback_data="출석")],
        [InlineKeyboardButton("🆘 구제", callback_data="구제")],
    ])


def game_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 주사위", callback_data="주사위")],
        [InlineKeyboardButton("🪙 동전", callback_data="동전")],
        [InlineKeyboardButton("🎰 슬롯", callback_data="슬롯")],
        [InlineKeyboardButton("🃏 바카라", callback_data="바카라")],
        [InlineKeyboardButton("⬅ 뒤로", callback_data="뒤로")],
    ])


# ================= START =================
async def 시작(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    create_user(uid)
    await update.message.reply_text("🎰 카지노 봇 시작!", reply_markup=main_menu())


async def 잔액(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)
    await update.message.reply_text(f"💰 잔액: {bal:,}")


async def 송금(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        target = int(context.args[0])
        amount = int(context.args[1])

        if amount <= 0:
            return await update.message.reply_text("❌ 금액 오류")

        if get_balance(uid) < amount:
            return await update.message.reply_text("❌ 잔액 부족")

        update_balance(uid, -amount, "송금_출금")
        update_balance(target, amount, "송금_입금")

        await update.message.reply_text("✅ 송금 완료")

    except:
        await update.message.reply_text("사용법: /송금 <유저ID> <금액>")


# ================= 출석 =================
async def 출석로직(uid, message):
    cur.execute("SELECT last_checkin FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if row and row[0] and row[0][:10] == now()[:10]:
        return await message.reply_text("❌ 오늘 이미 출석했습니다")

    reward = random.randint(CHECKIN_MIN, CHECKIN_MAX)
    update_balance(uid, reward, "출석")

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (now(), uid))
    conn.commit()

    await message.reply_text(f"🎁 출석 보상: +{reward:,}")


async def 출석(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await 출석로직(update.effective_user.id, update.message)


# ================= 구제 =================
async def 구제로직(uid, message):
    if get_balance(uid) != 0:
        return await message.reply_text("❌ 잔액 0일 때만 가능")

    update_balance(uid, RELIEF_AMOUNT, "구제")
    await message.reply_text(f"🆘 구제 지급: +{RELIEF_AMOUNT:,}")


async def 구제(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await 구제로직(update.effective_user.id, update.message)


# ================= 게임 =================
async def dice(chat):
    m = await chat.send_message("🎲 굴리는 중...")
    d = await chat.send_dice("🎲")
    await asyncio.sleep(2)
    await m.edit_text(f"🎲 결과: {d.dice.value}")


async def coin(chat):
    m = await chat.send_message("🪙 던지는 중...")
    d = await chat.send_dice("🎲")
    await asyncio.sleep(2)
    res = "앞면" if d.dice.value % 2 == 0 else "뒷면"
    await m.edit_text(f"🪙 결과: {res}")


async def slots(chat):
    m = await chat.send_message("🎰 스핀...")
    d = await chat.send_dice("🎰")
    await asyncio.sleep(3)
    await m.edit_text(f"🎰 결과: {d.dice.value}")


async def baccarat(chat):
    m = await chat.send_message("🃏 카드 배분...")
    p = random.randint(1, 10)
    b = random.randint(1, 10)

    await asyncio.sleep(1)
    await m.edit_text(f"플레이어: {p}")
    await asyncio.sleep(1)
    await m.edit_text(f"뱅커: {b}")

    if p > b:
        r = "플레이어 승"
    elif b > p:
        r = "뱅커 승"
    else:
        r = "무승부"

    await asyncio.sleep(1)
    await m.edit_text(f"결과: {r}")


# ================= CALLBACK =================
async def 버튼(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    data = q.data

    if data == "게임":
        await q.message.edit_text("🎮 게임 선택", reply_markup=game_menu())

    elif data == "잔액":
        await q.message.edit_text(f"💰 잔액: {get_balance(uid):,}", reply_markup=main_menu())

    elif data == "출석":
        await 출석로직(uid, q.message)

    elif data == "구제":
        await 구제로직(uid, q.message)

    elif data == "뒤로":
        await q.message.edit_text("🏠 메인", reply_markup=main_menu())

    elif data == "주사위":
        await dice(q.message.chat)

    elif data == "동전":
        await coin(q.message.chat)

    elif data == "슬롯":
        await slots(q.message.chat)

    elif data == "바카라":
        await baccarat(q.message.chat)


# ================= 관리자 =================
async def 지급(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])
    amount = int(context.args[1])

    update_balance(uid, amount, "관리자_지급")
    await update.message.reply_text("관리자 지급 완료")


async def 차감(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])
    amount = -abs(int(context.args[1]))

    update_balance(uid, amount, "관리자_차감")
    await update.message.reply_text("관리자 차감 완료")


async def 로그(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()

    await update.message.reply_text("\n".join(map(str, rows)))


async def 랭킹(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()

    text = "🏆 랭킹\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r[0]} - {r[1]:,}\n"

    await update.message.reply_text(text)


# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # 유저
    app.add_handler(CommandHandler("시작", 시작))
    app.add_handler(CommandHandler("잔액", 잔액))
    app.add_handler(CommandHandler("송금", 송금))
    app.add_handler(CommandHandler("출석", 출석))
    app.add_handler(CommandHandler("구제", 구제))

    # 관리자
    app.add_handler(CommandHandler("지급", 지급))
    app.add_handler(CommandHandler("차감", 차감))
    app.add_handler(CommandHandler("로그", 로그))
    app.add_handler(CommandHandler("랭킹", 랭킹))

    # UI
    app.add_handler(CallbackQueryHandler(버튼))

    print("카지노 봇 실행")
    app.run_polling()


if __name__ == "__main__":
    main()