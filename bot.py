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

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
# ===================================================

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не задан!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB = "promo.db"

# ==================== ТОВАРЫ ====================
# id: {stars, type, value, title, emoji}
PRODUCTS = {
    "coins_1k":   {"stars": 30,  "type": "coins", "value": 1000,   "title": "1 000 монет",    "emoji": "🪙"},
    "coins_6k":   {"stars": 150, "type": "coins", "value": 6000,   "title": "6 000 монет",    "emoji": "💰"},
    "coins_12k":  {"stars": 300, "type": "coins", "value": 12000,  "title": "12 000 монет",   "emoji": "💎"},
    "skin_random":{"stars": 150, "type": "skin",  "value": "random","title": "Случайный скин","emoji": "🎁"},
}


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
            used_at TEXT,
            reward_type TEXT,
            reward_value TEXT,
            stars_paid INTEGER
        )
    """)
    conn.commit()
    conn.close()


def generate_unique_code():
    """LAPKA-XXXX-XXXX (без префикса товара — защита от подбора)"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    for _ in range(50):  # 50 попыток
        p1 = secrets.token_hex(2).upper()
        p2 = secrets.token_hex(2).upper()
        code = f"LAPKA-{p1}-{p2}"
        c.execute("SELECT 1 FROM codes WHERE code=?", (code,))
        if not c.fetchone():
            conn.close()
            return code
    conn.close()
    raise RuntimeError("Не удалось сгенерировать уникальный код")


def save_code(code, user_id, product):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO codes (code, user_id, issued_at, reward_type, reward_value, stars_paid) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (code, user_id, datetime.utcnow().isoformat(),
         product["type"], str(product["value"]), product["stars"])
    )
    conn.commit()
    conn.close()


def verify_and_use_code(code):
    """Возвращает (valid, reward_type, reward_value) и помечает код использованным."""
    code = code.strip().upper()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT used, reward_type, reward_value FROM codes WHERE code=?", (code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, None, None, "not_found"
    used, rtype, rvalue = row
    if used:
        conn.close()
        return False, None, None, "already_used"
    c.execute("UPDATE codes SET used=1, used_at=? WHERE code=?",
              (datetime.utcnow().isoformat(), code))
    conn.commit()
    conn.close()
    return True, rtype, rvalue, "ok"


def stats():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM codes WHERE used=0")
    free = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM codes WHERE used=1")
    used = c.fetchone()[0]
    c.execute("SELECT SUM(stars_paid) FROM codes WHERE used=1")
    total_stars = c.fetchone()[0] or 0
    conn.close()
    return free, used, total_stars


# ==================== КЛАВИАТУРЫ ====================
def shop_kb():
    rows = []
    for pid, p in PRODUCTS.items():
        rows.append([InlineKeyboardButton(
            text=f"{p['emoji']} {p['title']} — {p['stars']} ⭐",
            callback_data=f"buy:{pid}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==================== ХЕНДЛЕРЫ ====================
@dp.message(CommandStart())
async def start_cmd(msg: Message):
    await msg.answer(
        "👋 <b>Магазин промокодов</b>\n\n"
        "🎮 Игра: <b>Ласка-Оборона NS-01</b>\n\n"
        "Выбери товар — оплатишь Stars и сразу получишь уникальный код.\n"
        "Введи код в игре — получишь награду. Один код = одна покупка.\n\n"
        "⭐ <i>Купить Stars можно в Telegram → Настройки → Telegram Stars</i>",
        reply_markup=shop_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("buy:"))
async def buy_cb(cb: CallbackQuery):
    pid = cb.data.split(":", 1)[1]
    if pid not in PRODUCTS:
        await cb.answer("Товар не найден", show_alert=True)
        return
    p = PRODUCTS[pid]
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title=p["title"],
        description=f"Промокод для игры «Ласка-Оборона NS-01»: {p['title']}",
        payload=f"buy:{pid}:{cb.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=p["title"], amount=p["stars"])],
    )
    await cb.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def payment_success(msg: Message):
    payload = msg.successful_payment.invoice_payload or ""
    parts = payload.split(":")
    if len(parts) < 3 or parts[0] != "buy":
        await msg.answer("⚠️ Ошибка: не удалось определить товар.")
        return
    pid = parts[1]
    if pid not in PRODUCTS:
        await msg.answer("⚠️ Ошибка: товар не найден.")
        return

    product = PRODUCTS[pid]
    code = generate_unique_code()
    save_code(code, msg.from_user.id, product)

    logging.info(f"💰 {msg.from_user.id} купил {pid} за {product['stars']} ⭐ → {code}")

    await msg.answer(
        f"✅ <b>Оплата получена!</b>\n\n"
        f"{product['emoji']} Товар: <b>{product['title']}</b>\n"
        f"⭐ Оплачено: <b>{product['stars']} Stars</b>\n\n"
        f"🎁 Твой промокод:\n\n<code>{code}</code>\n\n"
        f"📋 <i>Скопируй код (нажми на него) и введи в игре.</i>",
        parse_mode="HTML"
    )


# ==================== АДМИН-КОМАНДЫ ====================
@dp.message(F.from_user.id == ADMIN_ID, Command("stats"))
async def stats_cmd(msg: Message):
    free, used, stars = stats()
    await msg.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"🎫 Свободных кодов: <b>{free}</b>\n"
        f"✅ Продано: <b>{used}</b>\n"
        f"⭐ Всего Stars: <b>{stars}</b>",
        parse_mode="HTML"
    )


@dp.message(F.from_user.id == ADMIN_ID, Command("export"))
async def export_cmd(msg: Message):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT code, reward_type, reward_value FROM codes WHERE used=0")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await msg.answer("Нет свободных кодов.")
        return
    text = "\n".join(f"{r[0]} ({r[1]}:{r[2]})" for r in rows)
    if len(text) > 4000:
        text = text[:4000] + f"\n\n... (всего {len(rows)})"
    await msg.answer(f"📋 <b>Свободные коды:</b>\n\n<code>{text}</code>", parse_mode="HTML")


# ==================== ЗАПУСК ====================
async def main():
    init_db()
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
