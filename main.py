import os
import asyncio
from aiohttp import web
import logging

from bot import main as bot_main, verify_and_use_code

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


async def health(request):
    return web.Response(text="OK")


async def verify_code(request):
    """Эндпоинт для игры: /verify?code=LAPKA-XXXX-XXXX"""
    code = request.query.get("code", "")
    if not code:
        return web.json_response(
            {"valid": False, "reason": "no_code"},
            headers={"Access-Control-Allow-Origin": "*"}
        )
    valid, rtype, rvalue, reason = verify_and_use_code(code)
    if not valid:
        return web.json_response(
            {"valid": False, "reason": reason},
            headers={"Access-Control-Allow-Origin": "*"}
        )
    return web.json_response(
        {"valid": True, "reward_type": rtype, "reward_value": rvalue},
        headers={"Access-Control-Allow-Origin": "*"}
    )


async def options_handler(request):
    """CORS preflight"""
    return web.Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })


async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    app.router.add_get('/verify', verify_code)
    app.router.add_route('OPTIONS', '/verify', options_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"✅ Health-check + /verify на порту {port}")


async def run_all():
    await asyncio.gather(
        start_health_server(),
        bot_main()
    )


if __name__ == "__main__":
    asyncio.run(run_all())
