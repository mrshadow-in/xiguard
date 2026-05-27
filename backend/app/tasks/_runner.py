"""Helper to run async coroutines from sync Celery tasks."""
from __future__ import annotations

import asyncio
from typing import Coroutine, TypeVar

T = TypeVar("T")


def run(coro: Coroutine[None, None, T]) -> T:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("event loop already running")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
