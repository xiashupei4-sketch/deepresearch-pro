"""End-to-end API smoke test: create research, poll to completion, verify artifacts."""
import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8000"


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30, trust_env=False) as client:
        health = await client.get("/api/health")
        print("health:", health.json())

        resp = await client.post("/api/research", json={
            "query": "Compare hybrid retrieval and reranking approaches in RAG systems"})
        resp.raise_for_status()
        research = resp.json()
        rid = research["id"]
        print("created:", rid, research["status"])

        for i in range(60):
            await asyncio.sleep(5)
            s = (await client.get(f"/api/research/{rid}")).json()
            print(f"[{(i + 1) * 5}s] status={s['status']} tasks={s.get('tasks_count')}")
            if s["status"] in ("COMPLETED", "FAILED"):
                break

        print("final status:", s["status"], "error:", s.get("error"))
        tasks = (await client.get(f"/api/research/{rid}/tasks")).json()
        if isinstance(tasks, dict):
            tasks = tasks.get("tasks", [])
        print("tasks:", [(t["id"], t["status"]) for t in tasks])
        report = (await client.get(f"/api/research/{rid}/report")).json()
        rep = report.get("report") or ""
        print("report chars:", len(rep))
        ev = (await client.get(f"/api/research/{rid}/evidence")).json()
        evs = ev.get("evidence", ev) if isinstance(ev, dict) else ev
        print("evidence rows:", len(evs))
        evl = (await client.get(f"/api/research/{rid}/evaluation")).json()
        print("evaluation:", evl)
        return 0 if s["status"] == "COMPLETED" and rep else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
