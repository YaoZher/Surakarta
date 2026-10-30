"""Run with python -m server from the repository root."""
import argparse
import asyncio
import os
import signal

from networking.server import RoomService


async def run(args):
    service = await RoomService(
        reconnect_seconds=args.reconnect_seconds, max_rooms=args.max_rooms,
        max_connections=args.max_connections,
    ).start(args.host, args.port)
    print(f"Surakarta room server listening on {args.host}:{service.port}", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass  # Windows uses asyncio.run's KeyboardInterrupt handling.
    try:
        await stop.wait()
    finally:
        await service.close()


def main():
    parser = argparse.ArgumentParser(description="Surakarta authoritative room server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--reconnect-seconds", type=float, default=60)
    parser.add_argument("--max-rooms", type=int, default=128)
    parser.add_argument("--max-connections", type=int, default=256)
    try:
        asyncio.run(run(parser.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
