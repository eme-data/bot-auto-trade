import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


async def run_periodically(
    interval_seconds: int,
    coro_func: Callable[[], Awaitable[None]],
    name: str = "periodic-task",
) -> None:
    while True:
        try:
            await coro_func()
        except Exception as e:
            logger.exception("Error in periodic task '%s': %s", name, e)
        await asyncio.sleep(interval_seconds)
