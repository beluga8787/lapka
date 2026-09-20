import os
import asyncio
from aiohttp import web
import logging

from bot import main as bot_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


async def health(request):
    """Простой эндпоинт для проверки работоспособности сервиса."""
    return web.Response(text="OK")


async def start_health_server():
    """Запускает веб-сервер на порту, который предоставляет Render."""
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"✅ Health-check сервер запущен на порту {port}")


async def run_all():
    """Запускает health-сервер и Telegram-бота параллельно."""
    await asyncio.gather(
        start_health_server(),
        bot_main()
    )


if __name__ == "__main__":
    asyncio.run(run_all())