"""Worker entrypoint (``python -m app.worker``).

Sprint 1 ships a minimal long-running loop that initialises logging and the
worker pool and stays alive. Sprint 3 attaches the ingest queue consumer and the
LangGraph pipeline runner (with checkpoint recovery on startup).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from app.config import get_settings
from app.db.session import dispose_engine
from app.observability.logging import configure_logging, get_logger
from app.worker.pool import get_worker_pool

log = get_logger(__name__)


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    get_worker_pool()
    log.info("worker.started", env=settings.env.value)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # add_signal_handler is unavailable on some platforms (e.g. Windows).
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    finally:
        log.info("worker.stopping")
        await dispose_engine()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
