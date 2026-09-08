"""Windows-safe API launcher for TradePilot.

psycopg async requires SelectorEventLoop. On Windows + Python 3.14, uvicorn's
default loop is still Proactor even when the deprecated policy is set — so we
boot via asyncio.run(..., loop_factory=SelectorEventLoop).
"""
from __future__ import annotations

import argparse
import asyncio
import selectors
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TradePilot API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    import uvicorn

    config = uvicorn.Config(
        "app.main:app",
        host=args.host,
        port=args.port,
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    async def _serve() -> None:
        await server.serve()

    if sys.platform == "win32":
        asyncio.run(
            _serve(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(_serve())


if __name__ == "__main__":
    main()
