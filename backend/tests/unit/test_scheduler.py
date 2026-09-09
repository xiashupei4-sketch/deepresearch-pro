"""Unit tests — task scheduler dependency resolution (incl. cross-iteration fix)."""

from app.graph.scheduler import mark_task, select_runnable


def _t(id: str, deps: list[str] | None = None, status: str = "PENDING",
       order: int = 0) -> dict:
    return {"id": id, "title": id, "description": "", "task_type": "search",
            "priority": 1, "dependencies": deps or [], "status": status,
            "order_index": order}


def test_empty_when_no_tasks():
    assert select_runnable([]) == []


def test_no_deps_all_runnable():
    tasks = [_t("a"), _t("b"), _t("c")]
    runnable = select_runnable(tasks)
    assert [t["id"] for t in runnable] == ["a", "b", "c"]


def test_dependency_gating():
    tasks = [_t("a"), _t("b", deps=["a"]), _t("c", deps=["b"])]
    assert [t["id"] for t in select_runnable(tasks)] == ["a"]
    mark_task(tasks, "a", status="COMPLETED")
    assert [t["id"] for t in select_runnable(tasks)] == ["b"]
    mark_task(tasks, "b", status="COMPLETED")
    assert [t["id"] for t in select_runnable(tasks)] == ["c"]


def test_completed_ids_from_earlier_iterations():
    """Deps satisfied by tasks completed in an earlier iteration (no longer
    present in the pending list) must count as satisfied."""
    tasks = [_t("b", deps=["a"]), _t("c", deps=["a", "z"])]
    runnable = select_runnable(tasks, completed_ids={"a"})
    assert [t["id"] for t in runnable] == ["b"]
    # "z" never completed → c stays blocked
    assert all(t["id"] != "c" for t in runnable)


def test_priority_then_order_sorting():
    tasks = [
        {"id": "x", "title": "", "description": "", "task_type": "s", "priority": 2,
         "dependencies": [], "status": "PENDING", "order_index": 0},
        {"id": "y", "title": "", "description": "", "task_type": "s", "priority": 1,
         "dependencies": [], "status": "PENDING", "order_index": 5},
        {"id": "z", "title": "", "description": "", "task_type": "s", "priority": 1,
         "dependencies": [], "status": "PENDING", "order_index": 1},
    ]
    assert [t["id"] for t in select_runnable(tasks)] == ["z", "y", "x"]


def test_mark_task_mutates_in_place():
    tasks = [_t("a"), _t("b")]
    out = mark_task(tasks, "b", status="COMPLETED", result_summary="done")
    assert out is tasks
    assert tasks[1]["status"] == "COMPLETED"
    assert tasks[1]["result_summary"] == "done"
