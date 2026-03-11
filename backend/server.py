import asyncio
import json
import threading
from datetime import datetime, timezone
from aiohttp import web, WSMsgType
from pathlib import Path
from constants import DEFAULT_CITY, DEFAULT_INTERVAL_SECONDS
from weather_app.services import fetch_all_sources, geocode_city

# Store latest weather data in memory with thread safety
latest_data = None
latest_stats = {}
data_lock = threading.Lock()
connected_clients = set()





def build_payload(city: str, interval: int, data: list[dict], stats: dict) -> str:
    return json.dumps(
        {
            "city": city,
            "interval_seconds": interval,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "sources": data,
        }
    )

async def weather_fetcher(city, interval):
    global latest_data, latest_stats
    location = await asyncio.to_thread(geocode_city, city)

    while True:
        new_data, new_stats = await asyncio.to_thread(fetch_all_sources, location)
        
        with data_lock:
            latest_data = new_data
            latest_stats = new_stats
        
        message = build_payload(location.city, interval, latest_data, latest_stats)
        if connected_clients:
            disconnected = []
            for ws in connected_clients:
                try:
                    await ws.send_str(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                connected_clients.discard(ws)
        await asyncio.sleep(interval)

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_clients.add(ws)
    try:
        with data_lock:
            if latest_data:
                city = latest_data[0].get("city", DEFAULT_CITY) if latest_data else DEFAULT_CITY
                interval = request.app["interval_seconds"]
                await ws.send_str(build_payload(city, interval, latest_data.copy(), latest_stats.copy()))

        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        connected_clients.discard(ws)
    return ws

async def index(request):
    return web.FileResponse(Path(__file__).parent.parent / 'static' / 'index.html')

async def setup_app(city, interval):
    app = web.Application()
    app["interval_seconds"] = interval
    app.router.add_get('/', index)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_static('/static/', Path(__file__).parent.parent / 'static', show_index=True)

    async def on_startup(app):
        app['weather_task'] = asyncio.create_task(weather_fetcher(city, interval))

    async def on_cleanup(app):
        task = app.get('weather_task')
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--city', default=DEFAULT_CITY)
    parser.add_argument('--interval', type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    web.run_app(setup_app(args.city, args.interval), port=args.port)
