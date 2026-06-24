import unittest
from datetime import datetime, timedelta, timezone

from app.models.worker import Worker
from app.services.worker_binding import (
    worker_heartbeat_age_seconds,
    worker_heartbeat_status,
    worker_summary_fields,
)


def make_worker(*, status: str = "online", last_heartbeat_at: datetime | None) -> Worker:
    return Worker(
        id="worker-1",
        role="transit",
        status=status,
        worker_secret_hash="hash",
        last_heartbeat_at=last_heartbeat_at,
    )


class WorkerHeartbeatDisplayStatusTests(unittest.TestCase):
    def test_recent_online_worker_displays_online(self):
        current_time = datetime.now(timezone.utc)
        worker = make_worker(last_heartbeat_at=current_time - timedelta(minutes=1))

        self.assertEqual(worker_heartbeat_status(worker, current_time=current_time), "online")
        self.assertEqual(worker_heartbeat_age_seconds(worker, current_time=current_time), 60)
        fields = worker_summary_fields(worker)
        self.assertFalse(fields["worker_is_heartbeat_stale"])

    def test_old_online_worker_displays_stale(self):
        current_time = datetime.now(timezone.utc)
        worker = make_worker(last_heartbeat_at=current_time - timedelta(minutes=10))

        self.assertEqual(worker_heartbeat_status(worker, current_time=current_time), "stale")
        self.assertEqual(worker_heartbeat_age_seconds(worker, current_time=current_time), 600)

    def test_deleted_worker_displays_deleted(self):
        current_time = datetime.now(timezone.utc)
        worker = make_worker(status="deleted", last_heartbeat_at=current_time - timedelta(minutes=1))

        self.assertEqual(worker_heartbeat_status(worker, current_time=current_time), "deleted")

    def test_missing_heartbeat_displays_unknown(self):
        worker = make_worker(last_heartbeat_at=None)

        self.assertEqual(worker_heartbeat_status(worker), "unknown")
        self.assertIsNone(worker_heartbeat_age_seconds(worker))


if __name__ == "__main__":
    unittest.main()
