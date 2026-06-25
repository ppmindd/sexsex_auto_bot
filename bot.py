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

START_GOLD = 1_000_000
CHECKIN_MIN = 200_000
CHECKIN_MAX = 800_000
RELIEF_AMOUNT = 300_000

conn = sqlite3.connect("fish.db", check_same_thread=False)
cur = conn.cursor()

# ================= DB =================
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    gold INTEGER DEFAULT 0,
    exp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_checkin TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS fish_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    fish TEXT,
    rarity TEXT,
    value INTEGER,
    time TEXT
)
""")

conn.commit()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_user(uid):
    cur.execute("""
    INSERT OR IGNORE INTO users (user_id, gold, exp, level)
    VALUES (?, ?, 0, 1)
    """, (uid, START_GOLD))
    conn.commit()


def get_user(uid):
    cur.execute("SELECT gold, exp, level FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()


def update_gold(uid, amount):
    create_user(uid)
    gold, exp, lvl = get_user(uid)
    new_gold = gold + amount

    cur.execute("UPDATE users SET gold=? WHERE user_id=?", (new_gold, uid))
    conn.commit()

    return new_gold


# ================= LEVEL SYSTEM =================
def add_exp(uid, amount, message=None):
    gold, exp, lvl = get_user(uid)

    exp += amount
    need = lvl * 1000

    leveled = False

    while exp >= need:
        exp -= need
        lvl += 1
        need = lvl * 1000
        leveled = True

    cur.execute("UPDATE users SET exp=?, level=? WHERE user_id=?", (exp, lvl, uid))
    conn.commit()

    if leveled and message:
        asyncio.create_task(message.reply_text(f"🎉 레벨 업! Lv.{lvl}"))


# ================= FISH SYSTEM =================
fish_pool = [
    ("🐟 작은 물고기", "일반", 100),
    ("🐠 열대어", "일반", 200),
    ("🐡 복어", "희귀", 500),
    ("🦈 상어", "희귀", 1500),
    ("🐋 고래", "전설", 5000),
    ("🐉 해룡", "신화", 20000),
]


def catch_fish():
    # 확률 가중치
    roll = random.randint(1, 100)

    if roll <= 60:
        return random.choice(fish_pool[:2])
    elif roll <= 85:
        return random.choice(fish_pool[2:4])
    elif roll <= 97:
        return fish_pool[4]
    else:
        return fish_pool[5]


# ================= UI =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎣 낚시", callback_data="fish")],
        [InlineKeyboardButton("💰 골드", callback_data="gold")],
        [InlineKeyboardButton("📊 프로필", callback_data="profile")],
        [InlineKeyboardButton("🐟 도감", callback_data="log")],
        [InlineKeyboardButton("🎁 출석", callback_data="checkin")],
        [InlineKeyboardButton("🆘 구제", callback_data="relief")],
    ])


# ================= COMMAND =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    create_user(uid)
    await update.message.reply_text("🎣 낚시 RPG 시작!", reply_markup=main_menu())


async def gold_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    gold, exp, lvl = get_user(uid)
    await update.message.reply_text(f"💰 {gold:,} 골드 | ⭐ Lv.{lvl} | EXP {exp:,}")


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    gold, exp, lvl = get_user(uid)

    text = f"""
📊 낚시 프로필

💰 골드: {gold:,}
⭐ 레벨: {lvl}
📈 경험치: {exp:,}
🎣 상태: 낚시 중
"""
    await update.message.reply_text(text)


# ================= CHECKIN =================
async def checkin_logic(uid, message):
    cur.execute("SELECT last_checkin FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if row and row[0] and row[0][:10] == now()[:10]:
        return await message.reply_text("❌ 오늘 이미 출석")

    reward = random.randint(CHECKIN_MIN, CHECKIN_MAX)
    update_gold(uid, reward)
    add_exp(uid, 150, message)

    cur.execute("UPDATE users SET last_checkin=? WHERE user_id=?", (now(), uid))
    conn.commit()

    await message.reply_text(f"🎁 출석 +{reward:,} 골드")


async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await checkin_logic(update.effective_user.id, update.message)


# ================= RELIEF =================
async def relief_logic(uid, message):
    if get_user(uid)[0] != 0:
        return await message.reply_text("❌ 골드 0일 때만 가능")

    update_gold(uid, RELIEF_AMOUNT)
    add_exp(uid, 50, message)

    await message.reply_text(f"🆘 보급 +{RELIEF_AMOUNT:,}")


async def relief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await relief_logic(update.effective_user.id, update.message)


# ================= FISHING =================
async def fish_action(chat, uid):
    m = await chat.send_message("🎣 낚시 중...")
    fish, rarity, value = catch_fish()

    update_gold(uid, value)
    add_exp(uid, value // 10)

    cur.execute(
        "INSERT INTO fish_log (user_id, fish, rarity, value, time) VALUES (?, ?, ?, ?, ?)",
        (uid, fish, rarity, value, now())
    )
    conn.commit()

    await asyncio.sleep(2)
    await m.edit_text(f"🎣 {fish}\n⭐ {rarity}\n💰 +{value:,}")


# ================= CALLBACK =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    data = q.data

    if data == "fish":
        await fish_action(q.message.chat, uid)

    elif data == "gold":
        gold, exp, lvl = get_user(uid)
        await q.message.edit_text(f"💰 {gold:,} 골드 | Lv.{lvl}", reply_markup=main_menu())

    elif data == "profile":
        await profile(update, context)

    elif data == "checkin":
        await checkin_logic(uid, q.message)

    elif data == "relief":
        await relief_logic(uid, q.message)

    elif data == "log":
        cur.execute("SELECT fish, rarity, value FROM fish_log WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
        rows = cur.fetchall()

        text = "🐟 최근 낚시 기록\n\n"
        for r in rows:
            text += f"{r[0]} | {r[1]} | +{r[2]}\n"

        await q.message.edit_text(text, reply_markup=main_menu())


# ================= ADMIN =================
async def addgold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])
    amount = int(context.args[1])

    update_gold(uid, amount)
    await update.message.reply_text("admin ok")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cur.execute("SELECT * FROM fish_log ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()

    await update.message.reply_text("\n".join(map(str, rows)))


# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gold", gold_cmd))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("relief", relief))

    app.add_handler(CommandHandler("addgold", addgold))
    app.add_handler(CommandHandler("logs", logs))

    app.add_handler(CallbackQueryHandler(button))

    print("Fishing bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()