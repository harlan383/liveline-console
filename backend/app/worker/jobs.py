"""RQ compatibility module after legacy SSH/RQ flow removal.

LiveLine now uses the authenticated liveline-worker command channel for remote
actions. This module stays importable so the local RQ worker process can start,
but it intentionally exposes no legacy SSH job entry points.
"""


def rq_worker_placeholder_job() -> dict[str, str]:
    return {
        "status": "noop",
        "message": "Legacy SSH/RQ jobs were removed in Stage 3.3.72a; use Worker commands.",
    }
