# Ласка-Оборона — Telegram-бот для промокодов

Бот проверяет подписку на закрытый канал Boosty и выдаёт одноразовый промокод для игры.

## Переменные окружения

- `BOT_TOKEN` — токен от @BotFather
- `CHANNEL_ID` — ID закрытого канала (например, -1003954792992)
- `ADMIN_ID` — Telegram ID разработчика
- `BOOSTY_LINK` — ссылка на страницу Boosty
- `CHANNEL_LINK` — ссылка-приглашение в закрытый канал

## Команды админа

- `/gen 100` — сгенерировать 100 новых кодов
- `/stats` — статистика по кодам
- `/export` — выгрузить все свободные коды

## Деплой

1. Загрузить на GitHub
2. Создать Web Service на Render
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python main.py`
5. Задать переменные окружения
6. Настроить UptimeRobot на URL `/health` с интервалом 5 минут