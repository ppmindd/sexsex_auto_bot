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

conn = sqlite3.connect("fish.db", check_same_thread=False)
cur = conn.cursor()

# ================= DB SAFE INIT =================
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    gold INTEGER DEFAULT 0,
    exp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    rod INTEGER DEFAULT 1,
    bait INTEGER DEFAULT 0,
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
    INSERT OR IGNORE INTO users (user_id, gold, exp, level, rod, bait)
    VALUES (?, ?, 0, 1, 1, 0)
    """, (uid, START_GOLD))
    conn.commit()


def get_user(uid):
    cur.execute("SELECT gold, exp, level, rod, bait FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()


def save(uid, gold=None, exp=None, level=None, rod=None, bait=None):
    u = get_user(uid)
    if not u:
        create_user(uid)
        u = get_user(uid)

    g, e, l, r, b = u

    cur.execute("""
    UPDATE users SET gold=?, exp=?, level=?, rod=?, bait=? WHERE user_id=?
    """, (
        gold if gold is not None else g,
        exp if exp is not None else e,
        level if level is not None else l,
        rod if rod is not None else r,
        bait if bait is not None else b,
        uid
    ))
    conn.commit()


# ================= LEVEL =================
def add_exp(uid, amount, msg=None):
    gold, exp, lvl, rod, bait = get_user(uid)

    exp += amount
    need = lvl * 1000

    leveled = False

    while exp >= need:
        exp -= need
        lvl += 1
        need = lvl * 1000
        leveled = True

    save(uid, exp=exp, level=lvl)

    if leveled and msg:
        asyncio.create_task(msg.reply_text(f"🎉 레벨 업! Lv.{lvl}"))


# ================= FISH SYSTEM =================
def catch(rod, bait):
    roll = random.randint(1, 100)

    if bait > 0:
        roll -= 10

    roll -= (rod - 1) * 5
    roll = max(1, roll)

    if roll <= 60:
        return "🐟 작은 물고기", "일반", 100
    elif roll <= 85:
        return "🐠 열대어", "일반", 300
    elif roll <= 95:
        return "🦈 상어", "희귀", 2000
    elif roll <= 99:
        return "🐋 고래", "전설", 10000
    else:
        return "🐉 해룡", "신화", 50000


# ================= UI =================
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎣 낚시", callback_data="fish")],
        [InlineKeyboardButton("🛒 상점", callback_data="shop")],
        [InlineKeyboardButton("🎒 인벤토리", callback_data="inv")],
        [InlineKeyboardButton("📊 프로필", callback_data="profile")],
    ])


def shop():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪱 미끼 (50k)", callback_data="buy_bait")],
        [InlineKeyboardButton("🎣 낚싯대 업글 (300k)", callback_data="buy_rod2")],
        [InlineKeyboardButton("🎣 최종 낚싯대 (1M)", callback_data="buy_rod3")],
        [InlineKeyboardButton("⬅ 뒤로", callback_data="back")],
    ])


# ================= CORE =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    create_user(uid)
    await update.message.reply_text("🎣 낚시 RPG v2 시작!", reply_markup=menu())


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    g, e, l, r, b = get_user(uid)

    await update.message.reply_text(
        f"📊 프로필\n💰 {g:,}\n⭐ Lv.{l}\n📈 EXP {e:,}\n🎣 Rod Lv.{r}\n🪱 Bait {b}"
    )


# ================= FISH =================
async def fish_action(chat, uid):
    msg = await chat.send_message("🎣 낚는 중...")

    g, e, l, r, b = get_user(uid)

    fish, rarity, value = catch(r, b)

    save(uid, gold=g + value)

    add_exp(uid, value // 10, msg)

    cur.execute(
        "INSERT INTO fish_log (user_id, fish, rarity, value, time) VALUES (?, ?, ?, ?, ?)",
        (uid, fish, rarity, value, now())
    )
    conn.commit()

    await asyncio.sleep(2)
    await msg.edit_text(f"{fish}\n{rarity}\n+{value:,}")


# ================= SHOP =================
async def buy(uid, item, msg):
    g, e, l, r, b = get_user(uid)

    prices = {
        "bait": 50000,
        "rod2": 300000,
        "rod3": 1000000
    }

    if g < prices[item]:
        return await msg.reply_text("❌ 골드 부족")

    g -= prices[item]

    if item == "bait":
        b += 1
    elif item == "rod2":
        r = max(r, 2)
    elif item == "rod3":
        r = 3

    save(uid, gold=g, rod=r, bait=b)

    await msg.reply_text("✅ 구매 완료")


# ================= CALLBACK =================
async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    create_user(uid)

    d = q.data

    if d == "fish":
        await fish_action(q.message.chat, uid)

    elif d == "shop":
        await q.message.edit_text("🛒 상점", reply_markup=shop())

    elif d == "inv":
        g, e, l, r, b = get_user(uid)
        await q.message.edit_text(f"🎒 인벤\n🪱{b}\n🎣{r}", reply_markup=menu())

    elif d == "profile":
        await profile(update, context)

    elif d == "back":
        await q.message.edit_text("🏠 메인", reply_markup=menu())

    elif d == "buy_bait":
        await buy(uid, "bait", q.message)

    elif d == "buy_rod2":
        await buy(uid, "rod2", q.message)

    elif d == "buy_rod3":
        await buy(uid, "rod3", q.message)


# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CallbackQueryHandler(cb))

    print("Fishing v2 running")
    app.run_polling()


if __name__ == "__main__":
    main()