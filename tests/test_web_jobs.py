import threading
import time

import pytest

from web.jobs import DONE, FAILED, QUEUED, RUNNING, JobQueue, QueueFull


def make_queue(runner=None, **kwargs):
    runner = runner or (lambda job, progress: {"echo": job.prompt})
    return JobQueue(runner, autostart=False, **kwargs)


class TestLifecycle:
    def test_a_job_is_queued_then_done_with_its_result(self):
        queue = make_queue()
        job = queue.submit("playlist", prompt="neon")
        assert queue.snapshot(job.id)["status"] == QUEUED
        assert queue.run_pending() is True
        snapshot = queue.snapshot(job.id)
        assert snapshot["status"] == DONE and snapshot["result"] == {"echo": "neon"}
        assert (
            snapshot["started_at"] is not None and snapshot["finished_at"] is not None
        )

    def test_progress_is_recorded_as_the_job_runs(self):
        seen = {}

        def runner(job, progress):
            progress("taste")
            seen["during"] = queue.snapshot(job.id)
            progress("scout")
            return {}

        queue = make_queue(runner)
        job = queue.submit("playlist", prompt="x")
        queue.run_pending()
        assert (
            seen["during"]["status"] == RUNNING and seen["during"]["stage"] == "taste"
        )
        final = queue.snapshot(job.id)
        assert final["stage"] == "scout"
        assert [e["stage"] for e in final["events"]] == ["taste", "scout"]

    def test_a_failure_is_captured_and_does_not_stop_the_queue(self):
        def runner(job, progress):
            if job.prompt == "bad":
                raise RuntimeError("Spotify is down")
            return {"ok": True}

        queue = make_queue(runner)
        bad = queue.submit("playlist", prompt="bad")
        good = queue.submit("playlist", prompt="good")
        queue.run_pending()
        queue.run_pending()
        assert queue.snapshot(bad.id)["status"] == FAILED
        assert queue.snapshot(bad.id)["error"] == "Spotify is down"
        assert queue.snapshot(good.id)["status"] == DONE

    def test_an_error_without_a_message_still_says_something(self):
        def runner(job, progress):
            raise KeyError()

        queue = make_queue(runner)
        job = queue.submit("song")
        queue.run_pending()
        assert queue.snapshot(job.id)["error"] == "KeyError"

    def test_jobs_run_in_submission_order(self):
        order = []
        queue = make_queue(lambda job, progress: order.append(job.prompt) or {})
        for name in "abc":
            queue.submit("playlist", prompt=name)
        while queue.run_pending():
            pass
        assert order == ["a", "b", "c"]

    def test_nothing_pending(self):
        assert make_queue().run_pending() is False


class TestLimits:
    def test_the_queue_refuses_more_than_it_can_hold(self):
        queue = make_queue(max_queued=2)
        queue.submit("song")
        queue.submit("song")
        with pytest.raises(QueueFull):
            queue.submit("song")
        queue.run_pending()
        queue.submit("song")  # room again

    def test_old_finished_jobs_are_forgotten_so_memory_stays_flat(self):
        queue = make_queue(keep=3, max_queued=50)
        ids = [queue.submit("song", prompt=str(n)).id for n in range(10)]
        while queue.run_pending():
            pass
        queue.submit("song")  # trimming happens on submit
        kept = [j["id"] for j in queue.recent()]
        assert len(kept) == 4  # 3 finished + the new queued one
        assert ids[0] not in kept and ids[-1] in kept

    def test_recent_lists_newest_first(self):
        queue = make_queue()
        first = queue.submit("song")
        second = queue.submit("song")
        assert [j["id"] for j in queue.recent()] == [second.id, first.id]


class TestDiscardAndCommit:
    def test_a_queued_job_can_be_cancelled(self):
        queue = make_queue()
        job = queue.submit("song")
        assert queue.discard(job.id) is True
        assert queue.snapshot(job.id) is None
        assert queue.run_pending() is False

    def test_a_finished_job_can_be_dropped(self):
        queue = make_queue()
        job = queue.submit("song")
        queue.run_pending()
        assert queue.discard(job.id) is True

    def test_a_running_job_cannot_be_removed(self):
        results = {}

        def runner(job, progress):
            results["discard"] = queue.discard(job.id)
            return {}

        queue = make_queue(runner)
        queue.submit("song")
        queue.run_pending()
        assert results["discard"] is False

    def test_only_a_finished_preview_can_be_claimed_and_only_once(self):
        queue = make_queue()
        job = queue.submit("playlist", prompt="x", preview=True)
        with pytest.raises(ValueError):
            queue.claim_commit(job.id)  # not finished yet
        queue.run_pending()
        assert queue.claim_commit(job.id).committed is True
        with pytest.raises(ValueError, match="already"):
            queue.claim_commit(job.id)
        queue.release_commit(job.id)
        queue.claim_commit(job.id)  # released, so claimable again

    def test_a_real_run_is_not_a_preview(self):
        queue = make_queue()
        job = queue.submit("playlist", prompt="x", preview=False)
        queue.run_pending()
        with pytest.raises(ValueError):
            queue.claim_commit(job.id)

    def test_claiming_an_unknown_job(self):
        with pytest.raises(KeyError):
            make_queue().claim_commit("nope")


class TestWorkerThread:
    def test_the_background_worker_runs_jobs_one_at_a_time(self):
        running, peak, done = [0], [0], threading.Event()
        lock = threading.Lock()

        def runner(job, progress):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.05)
            with lock:
                running[0] -= 1
            if job.prompt == "last":
                done.set()
            return {}

        queue = JobQueue(runner, max_queued=5)
        try:
            for name in ("a", "b", "last"):
                queue.submit("song", prompt=name)
            assert done.wait(5)
        finally:
            queue.close()
        assert peak[0] == 1
