import asyncio
import logging
import os
import sqlite3
import secrets
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.enums import ChatMemberStatus

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CODE_PRICE_STARS = int(os.getenv("CODE_PRICE_STARS", "100"))  # цена в Stars
# ===================================================

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не задан!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB = "promo.db"


# ==================== БАЗА ====================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            used INTEGER DEFAULT 0,
            user_id INTEGER,
            issued_at TEXT,
            paid INTEGER DEFAULT 0
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


def stats():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM codes WHERE used=0")
    free = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM codes WHERE used=1")
    used = c.fetchone()[0]
    conn.close()
    return free, used


# ==================== КЛАВИАТУРЫ ====================
def buy_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Купить код — {CODE_PRICE_STARS} Stars",
            callback_data="buy_code"
        )],
    ])


# ==================== ХЕНДЛЕРЫ ====================
@dp.message(CommandStart())
async def start_cmd(msg: Message):
    await msg.answer(
        f"👋 Привет!\n\n"
        f"🎁 Здесь можно купить одноразовый промокод для игры «Ласка-Оборона NS-01».\n\n"
        f"💰 Цена: <b>{CODE_PRICE_STARS} Stars</b> за один код.\n"
        f"🔑 Один код = один раз активируется в игре.\n\n"
        f"Нажми кнопку ниже, чтобы купить:",
        reply_markup=buy_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "buy_code")
async def buy_cb(cb: CallbackQuery):
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title="Промокод для Ласка-Оборона NS-01",
        description=f"Одноразовый промокод. Активируется один раз в игре.",
        payload=f"promo_{cb.from_user.id}_{int(datetime.utcnow().timestamp())}",
        provider_token="",  # для Stars оставляем пустым
        currency="XTR",     # XTR = Telegram Stars
        prices=[LabeledPrice(label="Промокод", amount=CODE_PRICE_STARS)],
    )
    await cb.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    # Обязательно подтвердить в течение 10 секунд
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def payment_success(msg: Message):
    # Оплата прошла — выдаём код
    code = get_unused_code()
    if code:
        await msg.answer(
            f"✅ <b>Оплата получена!</b>\n\n"
            f"🎁 Твой промокод:\n\n<code>{code}</code>\n\n"
            f"Скопируй его и введи в игре «Ласка-Оборона NS-01».",
            parse_mode="HTML"
        )
        # Логируем покупку
        logging.info(f"Пользователь {msg.from_user.id} купил код {code}")
    else:
        await msg.answer(
            "⚠️ Оплата прошла, но коды закончились.\n"
            f"Напиши @твой_ник — выдам код вручную."
        )


# ==================== АДМИН-КОМАНДЫ ====================
@dp.message(F.from_user.id == ADMIN_ID, Command("gen"))
async def gen_cmd(msg: Message):
    parts = msg.text.split()
    count = int(parts[1]) if len(parts) > 1 else 100
    added = generate_codes(count)
    free, used = stats()
    await msg.answer(f"✅ Сгенерировано {added}.\nСвободных: {free}\nПродано: {used}")


@dp.message(F.from_user.id == ADMIN_ID, Command("stats"))
async def stats_cmd(msg: Message):
    free, used = stats()
    await msg.answer(f"📊 Статистика:\nСвободных: {free}\nПродано: {used}")


@dp.message(F.from_user.id == ADMIN_ID, Command("export"))
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
        text = text[:4000] + f"\n\n... (ещё {len(codes)} штук)"
    await msg.answer(f"📋 Свободные коды:\n\n<code>{text}</code>", parse_mode="HTML")


# ==================== ЗАПУСК ====================
async def main():
    init_db()
    free, _ = stats()
    if free == 0:
        generate_codes(50)
        logging.info("Сгенерировано 50 стартовых кодов")
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
