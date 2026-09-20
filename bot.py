import asyncio
import logging
import os
import sqlite3
import secrets
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ChatMemberStatus

# ==================== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003954792992"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BOOSTY_LINK = os.getenv("BOOSTY_LINK", "https://boosty.to/твой-ник")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/+hA9MFI38UaY5YTZi")

if not BOT_TOKEN:
    raise RuntimeError("❌ Переменная окружения BOT_TOKEN не задана!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB = "promo.db"


# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            used INTEGER DEFAULT 0,
            user_id INTEGER,
            issued_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS issued (
            user_id INTEGER PRIMARY KEY,
            code TEXT,
            issued_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def generate_codes(count=100, prefix="LAPKA"):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    added = 0
    for _ in range(count):
        p1 = secrets.token_hex(2).upper()
        p2 = secrets.token_hex(2).upper()
        code = f"{prefix}-{p1}-{p2}"
        try:
            c.execute("INSERT INTO codes (code) VALUES (?)", (code,))
            added += 1
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    conn.close()
    return added


def get_unused_code():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT code FROM codes WHERE used=0 LIMIT 1")
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    code = row[0]
    c.execute("UPDATE codes SET used=1, issued_at=? WHERE code=?",
              (datetime.utcnow().isoformat(), code))
    conn.commit()
    conn.close()
    return code


def get_user_code(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT code FROM issued WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def save_user_code(user_id, code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO issued (user_id, code, issued_at) VALUES (?, ?, ?)",
              (user_id, code, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def stats():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM codes WHERE used=0")
    free = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM codes WHERE used=1")
    used = c.fetchone()[0]
    conn.close()
    return free, used


# ==================== ПРОВЕРКА ПОДПИСКИ ====================
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        ]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False


# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check")],
    ])


# ==================== ХЕНДЛЕРЫ ====================
@dp.message(CommandStart())
async def start_cmd(msg: Message):
    user_id = msg.from_user.id
    existing = get_user_code(user_id)
    if existing:
        await msg.answer(
            f"🎁 Твой промокод:\n\n<code>{existing}</code>\n\n"
            f"Скопируй его и введи в игре «Ласка-Оборона NS-01».",
            parse_mode="HTML"
        )
        return

    if await is_subscribed(user_id):
        code = get_unused_code()
        if code:
            save_user_code(user_id, code)
            await msg.answer(
                f"✅ <b>Подписка подтверждена!</b>\n\n"
                f"🎁 Твой одноразовый промокод:\n\n<code>{code}</code>\n\n"
                f"Скопируй его и введи в игре.",
                parse_mode="HTML"
            )
        else:
            await msg.answer("😔 Коды закончились. Напиши разработчику.")
    else:
        await msg.answer(
            "👋 Привет! Чтобы получить промокод:\n\n"
            "1. Оформи подписку на Boosty\n"
            "2. Получи доступ к закрытому каналу\n"
            "3. Нажми «Я подписался» ниже",
            reply_markup=main_kb(),
            parse_mode="HTML"
        )


@dp.callback_query(F.data == "check")
async def check_cb(cb: CallbackQuery):
    user_id = cb.from_user.id
    existing = get_user_code(user_id)
    if existing:
        await cb.message.answer(
            f"🎁 Твой промокод:\n\n<code>{existing}</code>",
            parse_mode="HTML"
        )
        await cb.answer()
        return

    if await is_subscribed(user_id):
        code = get_unused_code()
        if code:
            save_user_code(user_id, code)
            await cb.message.answer(
                f"✅ Подписка подтверждена!\n\n🎁 Твой код:\n\n<code>{code}</code>",
                parse_mode="HTML"
            )
        else:
            await cb.message.answer("😔 Коды закончились.")
    else:
        await cb.answer("❌ Ты ещё не подписан на канал", show_alert=True)


# ==================== КОМАНДЫ АДМИНА ====================
@dp.message(F.from_user.id == ADMIN_ID, F.text.startswith("/gen"))
async def gen_cmd(msg: Message):
    parts = msg.text.split()
    count = int(parts[1]) if len(parts) > 1 else 100
    added = generate_codes(count)
    free, used = stats()
    await msg.answer(f"✅ Сгенерировано {added} кодов.\nСвободных: {free}\nВыдано: {used}")


@dp.message(F.from_user.id == ADMIN_ID, F.text == "/stats")
async def stats_cmd(msg: Message):
    free, used = stats()
    await msg.answer(f"📊 Статистика:\nСвободных: {free}\nВыдано: {used}")


@dp.message(F.from_user.id == ADMIN_ID, F.text == "/export")
async def export_cmd(msg: Message):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT code FROM codes WHERE used=0")
    codes = [row[0] for row in c.fetchall()]
    conn.close()
    if not codes:
        await msg.answer("Нет свободных кодов.")
        return
    text = "\n".join(codes)
    if len(text) > 4000:
        text = text[:4000] + f"\n\n... и ещё {len(codes) - text.count(chr(10)) - 1}"
    await msg.answer(f"📋 Свободные коды:\n\n<code>{text}</code>", parse_mode="HTML")


# ==================== ЗАПУСК ====================
async def main():
    init_db()
    free, _ = stats()
    if free == 0:
        generate_codes(100)
        logging.info("Сгенерировано 100 стартовых кодов")
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())