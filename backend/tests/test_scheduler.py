"""Core periodic scheduler behaviour."""

from core.scheduler import PeriodicJob, Scheduler


async def test_run_on_start_enqueues_after_restart(monkeypatch):
    calls: list[str] = []

    async def fake_enqueue(kind, payload, *, idempotency_key=None, **_kwargs):
        assert kind == "scheduler.job"
        calls.append(str(idempotency_key))

    monkeypatch.setattr("core.scheduler.enqueue", fake_enqueue)

    async def handler():
        return None

    def job() -> PeriodicJob:
        return PeriodicJob(
            key="demo.job",
            owner="test",
            handler=handler,
            interval_seconds=900,
            run_on_start=True,
        )

    first = Scheduler()
    first.register(job())
    await first._enqueue_due(1000.0)
    assert len(calls) == 1 and ":startup:" in calls[0]

    # The same interval bucket must not run twice in one process.
    await first._enqueue_due(1000.0)
    assert len(calls) == 1

    # A later bucket still runs normally.
    await first._enqueue_due(1900.0)
    assert len(calls) == 2 and ":startup:" not in calls[1]

    # A new process (scheduler instance) runs on start even in the same bucket.
    second = Scheduler()
    second.register(job())
    await second._enqueue_due(1000.0)
    assert len(calls) == 3 and ":startup:" in calls[2]
