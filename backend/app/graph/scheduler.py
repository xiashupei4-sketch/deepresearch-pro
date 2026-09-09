"""Task scheduler — dependency resolution with bounded parallelism."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


def select_runnable(tasks: list[dict], completed_ids: set[str] | None = None) -> list[dict]:
    """Tasks that are PENDING and whose dependencies are all COMPLETED.

    ``completed_ids`` may include ids of tasks completed in earlier iterations
    (they are no longer part of the pending list).
    """
    completed = set(completed_ids or set())
    completed |= {t["id"] for t in tasks if t.get("status") == "COMPLETED"}
    runnable = []
    for t in tasks:
        if t.get("status") != "PENDING":
            continue
        deps = t.get("dependencies") or []
        if all(d in completed for d in deps):
            runnable.append(t)
    runnable.sort(key=lambda t: (t.get("priority", 3), t.get("order_index", 0)))
    return runnable


async def run_parallel(items: list[Any], worker: Callable[[Any], Awaitable],
                       max_concurrency: int = 3) -> list[Any]:
    """asyncio.gather + Semaphore — never exceeds max_concurrency workers."""
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def guarded(item):
        async with semaphore:
            return await worker(item)

    return list(await asyncio.gather(*(guarded(i) for i in items)))


def mark_task(tasks: list[dict], task_id: str, *, status: str | None = None,
              **fields) -> list[dict]:
    for t in tasks:
        if t["id"] == task_id:
            if status:
                t["status"] = status
            t.update(fields)
    return tasks


def snapshot_status_block(tasks: list[dict]) -> str:
    lines = []
    for t in tasks:
        lines.append(f"- [{t.get('status', '?')}] {t['id']}: {t['title']}")
    return "\n".join(lines) or "(no tasks)"
