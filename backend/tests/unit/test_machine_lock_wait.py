import asyncio
import threading
import time
from types import SimpleNamespace

from starlette.requests import Request

from app.core.machine import check_bound_machine


def test_database_lock_wait_does_not_block_other_requests():
    started = threading.Event()
    release = threading.Event()

    class WaitingDatabase:
        def scalar(self, statement):
            started.set()
            release.wait(timeout=0.5)
            return None

    async def scenario():
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/workstation/tasks",
                "query_string": b"workstation_id=1",
                "headers": [],
            }
        )
        started_at = time.monotonic()
        task = asyncio.create_task(
            check_bound_machine(request, SimpleNamespace(company_id=1), WaitingDatabase())
        )
        try:
            await asyncio.sleep(0.03)
            assert started.is_set()
            # A second request/timer must run while the first is waiting for its row lock.
            assert time.monotonic() - started_at < 0.25
        finally:
            release.set()
            await task

    asyncio.run(scenario())
