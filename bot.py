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
        [InlineKeyboardButton("🎮 게임", callback_data="games")],
        [InlineKeyboardButton("💰 잔액", callback_data="balance")],
        [InlineKeyboardButton("🎁 출석", callback_data="checkin")],
        [InlineKeyboardButton("🆘 구제", callback_data="relief")],
    ])


def game_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 주사위", callback_data="dice")],
        [InlineKeyboardButton("🪙 동전", callback_data="coin")],
        [InlineKeyboardButton("🎰 슬롯", callback_data="slots")],
        [InlineKeyboardButton("🃏 바카라", callback_data="baccarat")],
        [InlineKeyboardButton("⬅ 뒤로", callback_data="back")],
    ])


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    create_user(uid)

    await update.message.reply_text("🎰 카지노 봇 시작!", reply_markup=main_menu())


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)
    await update.message.reply_text(f"💰 잔액: {bal:,}")


async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        target = int(context.args[0])
        amount = int(context.args[1])

        if amount <= 0:
            return await update.message.reply_text("❌ 금액 오류")

        if get_balance(uid) < amount:
            return await update.message.reply_text("❌ 잔액 부족")

        update_balance(uid, -amount, "transfer_out")
        update_balance(target, amount, "transfer_in")

        await update.message.reply_text("✅ 송금 완료")

    except:
        await update.message.reply_text("사용법: /transfer <유저ID> <금액>")


# ================= CHECKIN =================
async def checkin_logic(uid, message):
    cur.execute("SELECT last_checkin FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if row and row[0] and row[0][:10] == now()[:10]:
        return await message.reply_text("❌ 이미 출석했습니다")

    reward = random.randint(CHECKIN_MIN, CHECKIN_MAX)
    update_balance(uid, reward, "checkin")

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (now(), uid))
    conn.commit()

    await message.reply_text(f"🎁 출석 보상: +{reward:,}")


async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await checkin_logic(update.effective_user.id, update.message)


# ================= RELIEF =================
async def relief_logic(uid, message):
    if get_balance(uid) != 0:
        return await message.reply_text("❌ 잔액이 0일 때만 가능")

    update_balance(uid, RELIEF_AMOUNT, "relief")
    await message.reply_text(f"🆘 구제 지급: +{RELIEF_AMOUNT:,}")


async def relief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await relief_logic(update.effective_user.id, update.message)


# ================= GAMES =================
async def dice_game(chat, msg):
    m = await chat.send_message("🎲 굴리는 중...")
    d = await chat.send_dice("🎲")
    await asyncio.sleep(2)
    await m.edit_text(f"🎲 결과: {d.dice.value}")


async def coin_game(chat, msg):
    m = await chat.send_message("🪙 던지는 중...")
    d = await chat.send_dice("🎲")
    await asyncio.sleep(2)
    res = "앞면" if d.dice.value % 2 == 0 else "뒷면"
    await m.edit_text(f"🪙 결과: {res}")


async def slots_game(chat, msg):
    m = await chat.send_message("🎰 스핀...")
    d = await chat.send_dice("🎰")
    await asyncio.sleep(3)
    await m.edit_text(f"🎰 결과: {d.dice.value}")


async def baccarat_game(chat, msg):
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


# ================= CALLBACK (UI FIX 핵심) =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    data = q.data

    if data == "games":
        await q.message.edit_text("🎮 게임 선택", reply_markup=game_menu())

    elif data == "balance":
        bal = get_balance(uid)
        await q.message.edit_text(f"💰 잔액: {bal:,}", reply_markup=main_menu())

    elif data == "checkin":
        await checkin_logic(uid, q.message)

    elif data == "relief":
        await relief_logic(uid, q.message)

    elif data == "back":
        await q.message.edit_text("🏠 메인 메뉴", reply_markup=main_menu())

    elif data == "dice":
        await dice_game(q.message.chat, q.message)

    elif data == "coin":
        await coin_game(q.message.chat, q.message)

    elif data == "slots":
        await slots_game(q.message.chat, q.message)

    elif data == "baccarat":
        await baccarat_game(q.message.chat, q.message)


# ================= ADMIN =================
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

    text = "\n".join(map(str, rows))
    await update.message.reply_text(text)


async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()

    text = "🏆 랭킹\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r[0]} - {r[1]:,}\n"

    await update.message.reply_text(text)


# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("transfer", transfer))
    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("relief", relief))

    app.add_handler(CommandHandler("addmoney", addmoney))
    app.add_handler(CommandHandler("removemoney", removemoney))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("rank", rank))

    app.add_handler(CallbackQueryHandler(button))

    print("RUNNING...")
    app.run_polling()


if __name__ == "__main__":
    main()