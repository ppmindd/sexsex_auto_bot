import os
import asyncio
import random
import sqlite3
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {7381851504}

INITIAL_BALANCE = 1_000_000
CHECKIN_MIN = 1_000_000
CHECKIN_MAX = 3_000_000
RELIEF_AMOUNT = 500_000

conn = sqlite3.connect("casino.db", check_same_thread=False)
cur = conn.cursor()

# ================= DB =================
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    exp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
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
    cur.execute("""
    INSERT OR IGNORE INTO users (user_id, balance, exp, level)
    VALUES (?, ?, 0, 1)
    """, (uid, INITIAL_BALANCE))
    conn.commit()


def get_user(uid):
    cur.execute("SELECT balance, exp, level FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()


def update_balance(uid, amount, action=""):
    create_user(uid)
    bal, exp, lvl = get_user(uid)
    new_bal = bal + amount

    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, uid))
    conn.commit()

    cur.execute(
        "INSERT INTO logs (user_id, action, amount, balance, time) VALUES (?, ?, ?, ?, ?)",
        (uid, action, amount, new_bal, now()),
    )
    conn.commit()

    return new_bal


# ================= LEVEL SYSTEM =================
def add_exp(uid, amount, message=None):
    bal, exp, lvl = get_user(uid)

    exp += amount

    # 레벨업 기준 (단순 구조)
    needed = lvl * 1000

    leveled_up = False

    while exp >= needed:
        exp -= needed
        lvl += 1
        needed = lvl * 1000
        leveled_up = True

    cur.execute(
        "UPDATE users SET exp=?, level=? WHERE user_id=?",
        (exp, lvl, uid),
    )
    conn.commit()

    if leveled_up and message:
        asyncio.create_task(message.reply_text(f"🎉 레벨 업! Lv.{lvl}"))


# ================= UI =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 게임", callback_data="games")],
        [InlineKeyboardButton("💰 잔액", callback_data="balance")],
        [InlineKeyboardButton("📊 프로필", callback_data="profile")],
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


# ================= COMMAND =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    create_user(uid)
    await update.message.reply_text("🎰 카지노 + 레벨 시스템 시작!", reply_markup=main_menu())


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal, exp, lvl = get_user(uid)
    await update.message.reply_text(f"💰 {bal:,} | ⭐ Lv.{lvl} | EXP {exp:,}")


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal, exp, lvl = get_user(uid)

    text = f"""
📊 프로필

💰 잔액: {bal:,}
⭐ 레벨: {lvl}
📈 경험치: {exp:,}

🎮 활동: 카지노 플레이 중
"""
    await update.message.reply_text(text)


async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        target = int(context.args[0])
        amount = int(context.args[1])

        if amount <= 0:
            return await update.message.reply_text("❌ 금액 오류")

        if get_user(uid)[0] < amount:
            return await update.message.reply_text("❌ 잔액 부족")

        update_balance(uid, -amount, "transfer_out")
        update_balance(target, amount, "transfer_in")

        add_exp(uid, 50, update.message)

        await update.message.reply_text("✅ 송금 완료 + EXP 50")

    except:
        await update.message.reply_text("사용법: /transfer <id> <amount>")


# ================= CHECKIN =================
async def checkin_logic(uid, message):
    cur.execute("SELECT last_checkin FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if row and row[0] and row[0][:10] == now()[:10]:
        return await message.reply_text("❌ 오늘 이미 출석")

    reward = random.randint(CHECKIN_MIN, CHECKIN_MAX)
    update_balance(uid, reward, "checkin")
    add_exp(uid, 200, message)

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (now(), uid))
    conn.commit()

    await message.reply_text(f"🎁 출석 +{reward:,} / EXP +200")


async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await checkin_logic(update.effective_user.id, update.message)


# ================= RELIEF =================
async def relief_logic(uid, message):
    if get_user(uid)[0] != 0:
        return await message.reply_text("❌ 0일 때만 가능")

    update_balance(uid, RELIEF_AMOUNT, "relief")
    add_exp(uid, 100, message)

    await message.reply_text(f"🆘 구제 +{RELIEF_AMOUNT:,}")


async def relief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await relief_logic(update.effective_user.id, update.message)


# ================= GAMES =================
async def dice(chat):
    m = await chat.send_message("🎲")
    d = await chat.send_dice("🎲")
    await asyncio.sleep(2)
    await m.edit_text(f"🎲 {d.dice.value}")


async def coin(chat):
    m = await chat.send_message("🪙")
    d = await chat.send_dice("🎲")
    await asyncio.sleep(2)
    res = "앞면" if d.dice.value % 2 == 0 else "뒷면"
    await m.edit_text(f"🪙 {res}")


async def slots(chat):
    m = await chat.send_message("🎰")
    d = await chat.send_dice("🎰")
    await asyncio.sleep(3)
    await m.edit_text(f"🎰 {d.dice.value}")


async def baccarat(chat):
    m = await chat.send_message("🃏")
    p = random.randint(1, 10)
    b = random.randint(1, 10)

    await asyncio.sleep(1)
    await m.edit_text(f"P:{p}")
    await asyncio.sleep(1)
    await m.edit_text(f"B:{b}")

    if p > b:
        r = "P WIN"
    elif b > p:
        r = "B WIN"
    else:
        r = "DRAW"

    await asyncio.sleep(1)
    await m.edit_text(r)


# ================= CALLBACK =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    data = q.data

    if data == "games":
        await q.message.edit_text("🎮 Games", reply_markup=game_menu())

    elif data == "balance":
        bal, exp, lvl = get_user(uid)
        await q.message.edit_text(f"💰 {bal:,} | Lv.{lvl} | EXP {exp:,}", reply_markup=main_menu())

    elif data == "profile":
        await profile(update, context)

    elif data == "checkin":
        await checkin_logic(uid, q.message)

    elif data == "relief":
        await relief_logic(uid, q.message)

    elif data == "back":
        await q.message.edit_text("🏠 Main", reply_markup=main_menu())

    elif data == "dice":
        await dice(q.message.chat)
        add_exp(uid, 30, q.message)

    elif data == "coin":
        await coin(q.message.chat)
        add_exp(uid, 30, q.message)

    elif data == "slots":
        await slots(q.message.chat)
        add_exp(uid, 50, q.message)

    elif data == "baccarat":
        await baccarat(q.message.chat)
        add_exp(uid, 70, q.message)


# ================= ADMIN =================
async def addmoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])
    amount = int(context.args[1])

    update_balance(uid, amount, "admin_add")
    add_exp(uid, 20)

    await update.message.reply_text("admin ok")


async def removemoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])
    amount = -abs(int(context.args[1]))

    update_balance(uid, amount, "admin_remove")
    await update.message.reply_text("admin ok")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()

    await update.message.reply_text("\n".join(map(str, rows)))


async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()

    text = "🏆 RANK\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r[0]} - {r[1]:,}\n"

    await update.message.reply_text(text)


# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("profile", profile))
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