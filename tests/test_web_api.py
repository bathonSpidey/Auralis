import pytest
from fastapi.testclient import TestClient

from agent.schemas import PlaylistOutcome, SongOutcome, TrackInfo
from models.device import Device
from store.history import Store
from web.app import create_app, make_runner
from web.jobs import JobQueue


def track(n):
    return TrackInfo(uri=f"spotify:track:{n}", title=f"Song {n}", artist=f"Artist {n}")


class FakeAuralis:
    """Records what the web layer asks for."""

    def __init__(self, store):
        self.store = store
        self.calls = []

    def playlist_generator(self, prompt, depth, dry_run, device_id, source, progress):
        self.calls.append(("playlist", prompt, depth.value, dry_run, device_id, source))
        progress("scout")
        outcome = PlaylistOutcome(
            name="Mix",
            reason="because",
            research="notes",
            playlist_url=None if dry_run else "https://open.spotify.com/playlist/p1",
            tracks=[track(1), track(2)],
            playback="none",
            dry_run=dry_run,
        )
        if not dry_run:
            outcome.id = self.store.record_playlist(
                outcome, prompt, depth.value, source
            )
        return outcome

    def song_of_the_moment_suggestion(
        self, depth, dry_run, device_id, source, progress
    ):
        self.calls.append(("song", depth.value, dry_run, device_id, source))
        outcome = SongOutcome(
            track=track(9), reason="because", playback="none", dry_run=dry_run
        )
        if not dry_run:
            outcome.id = self.store.record_song(outcome, depth.value, source)
        return outcome

    def commit_playlist(self, preview, prompt, depth, device_id, source):
        self.calls.append(("commit_playlist", prompt, depth.value, device_id))
        result = preview.model_copy(
            update={
                "dry_run": False,
                "playlist_url": "https://open.spotify.com/playlist/p1",
            }
        )
        result.id = self.store.record_playlist(result, prompt, depth.value, source)
        return result

    def commit_song(self, preview, depth, device_id, source):
        self.calls.append(("commit_song", depth.value, device_id))
        result = preview.model_copy(update={"dry_run": False})
        result.id = self.store.record_song(result, depth.value, source)
        return result


class FakeSpotify:
    def __init__(self, broken=False):
        self.broken = broken

    def devices(self):
        if self.broken:
            raise RuntimeError("Spotify is unreachable")
        return [Device(id="kitchen", is_active=False, name="Kitchen", type="Speaker")]

    def logged_in(self):
        return not self.broken


@pytest.fixture
def world(tmp_path):
    store = Store(tmp_path / "api.db")
    auralis = FakeAuralis(store)
    holder = {}
    queue = JobQueue(
        make_runner(auralis, lambda job_id: holder["queue"].get(job_id)),
        autostart=False,
    )
    holder["queue"] = queue
    client = TestClient(create_app(auralis, store, FakeSpotify(), queue=queue))

    class World:
        pass

    w = World()
    w.client, w.queue, w.auralis, w.store = client, queue, auralis, store

    def run_all():
        while queue.run_pending():
            pass

    w.run_all = run_all
    return w


def submit(world, **body):
    response = world.client.post("/api/jobs", json=body)
    assert response.status_code == 202, response.text
    return response.json()


class TestCreatingJobs:
    def test_a_playlist_job_runs_and_returns_the_outcome(self, world):
        job = submit(world, kind="playlist", prompt="neon drive", depth="deep")
        assert job["status"] == "queued" and job["depth"] == "deep"
        world.run_all()
        done = world.client.get(f"/api/jobs/{job['id']}").json()
        assert done["status"] == "done"
        assert done["result"]["kind"] == "playlist"
        assert done["result"]["outcome"]["name"] == "Mix"
        assert world.auralis.calls[0] == (
            "playlist",
            "neon drive",
            "deep",
            False,
            None,
            "web",
        )

    def test_default_depths_differ_by_kind(self, world):
        submit(world, kind="playlist", prompt="x")
        submit(world, kind="song")
        world.run_all()
        assert world.auralis.calls[0][2] == "auto"
        assert world.auralis.calls[1][1] == "quick"

    def test_device_and_preview_are_passed_through(self, world):
        submit(world, kind="playlist", prompt="x", device_id="kitchen", preview=True)
        world.run_all()
        assert world.auralis.calls[0][3:5] == (True, "kitchen")

    def test_a_playlist_needs_a_prompt(self, world):
        response = world.client.post(
            "/api/jobs", json={"kind": "playlist", "prompt": "  "}
        )
        assert response.status_code == 422
        assert "Describe the playlist" in response.text

    def test_a_song_needs_no_prompt(self, world):
        assert submit(world, kind="song")["kind"] == "song"

    def test_unknown_kind_or_depth_is_rejected(self, world):
        assert world.client.post("/api/jobs", json={"kind": "album"}).status_code == 422
        bad = {"kind": "song", "depth": "extreme"}
        assert world.client.post("/api/jobs", json=bad).status_code == 422

    def test_a_full_queue_answers_429(self, world):
        for _ in range(3):
            submit(world, kind="song")
        response = world.client.post("/api/jobs", json={"kind": "song"})
        assert response.status_code == 429

    def test_unknown_job(self, world):
        assert world.client.get("/api/jobs/nope").status_code == 404

    def test_a_failing_run_reports_its_error(self, world):
        def boom(*args, **kwargs):
            raise RuntimeError("Claude is not logged in")

        world.auralis.playlist_generator = boom
        job = submit(world, kind="playlist", prompt="x")
        world.run_all()
        failed = world.client.get(f"/api/jobs/{job['id']}").json()
        assert failed["status"] == "failed" and "not logged in" in failed["error"]

    def test_listing_jobs(self, world):
        submit(world, kind="song")
        assert len(world.client.get("/api/jobs").json()["jobs"]) == 1


class TestPreviewThenCreate:
    def test_a_preview_creates_nothing_until_confirmed(self, world):
        job = submit(world, kind="playlist", prompt="x", preview=True)
        world.run_all()
        assert world.store.history() == []
        commit = world.client.post(f"/api/jobs/{job['id']}/create")
        assert commit.status_code == 202
        world.run_all()
        final = world.client.get(f"/api/jobs/{commit.json()['id']}").json()
        assert final["status"] == "done"
        assert final["result"]["outcome"]["dry_run"] is False
        assert final["result"]["outcome"]["playlist_url"].endswith("/p1")
        assert [c[0] for c in world.auralis.calls] == ["playlist", "commit_playlist"]
        assert world.auralis.calls[1][1] == "x"  # the original prompt travels along
        assert len(world.store.history()) == 1

    def test_a_preview_song_is_committed_as_a_song(self, world):
        job = submit(world, kind="song", preview=True)
        world.run_all()
        commit = world.client.post(f"/api/jobs/{job['id']}/create").json()
        world.run_all()
        final = world.client.get(f"/api/jobs/{commit['id']}").json()
        assert final["result"]["kind"] == "song"
        assert world.auralis.calls[-1][0] == "commit_song"

    def test_a_preview_can_only_be_created_once(self, world):
        job = submit(world, kind="playlist", prompt="x", preview=True)
        world.run_all()
        assert world.client.post(f"/api/jobs/{job['id']}/create").status_code == 202
        assert world.client.post(f"/api/jobs/{job['id']}/create").status_code == 409
        world.run_all()
        assert len(world.store.history()) == 1

    def test_a_real_run_cannot_be_created_again(self, world):
        job = submit(world, kind="playlist", prompt="x")
        world.run_all()
        assert world.client.post(f"/api/jobs/{job['id']}/create").status_code == 409

    def test_creating_before_the_preview_finishes_is_refused(self, world):
        job = submit(world, kind="playlist", prompt="x", preview=True)
        assert world.client.post(f"/api/jobs/{job['id']}/create").status_code == 409

    def test_creating_an_unknown_preview(self, world):
        assert world.client.post("/api/jobs/nope/create").status_code == 404

    def test_a_full_queue_leaves_the_preview_claimable(self, world):
        job = submit(world, kind="playlist", prompt="x", preview=True)
        world.run_all()
        for _ in range(3):
            submit(world, kind="song")
        assert world.client.post(f"/api/jobs/{job['id']}/create").status_code == 429
        world.run_all()
        assert world.client.post(f"/api/jobs/{job['id']}/create").status_code == 202

    def test_the_chosen_device_is_used_when_creating(self, world):
        job = submit(world, kind="playlist", prompt="x", preview=True)
        world.run_all()
        world.client.post(f"/api/jobs/{job['id']}/create?device_id=kitchen")
        world.run_all()
        assert world.auralis.calls[-1][3] == "kitchen"

    def test_discarding_a_preview(self, world):
        job = submit(world, kind="playlist", prompt="x", preview=True)
        world.run_all()
        assert world.client.delete(f"/api/jobs/{job['id']}").status_code == 204
        assert world.client.get(f"/api/jobs/{job['id']}").status_code == 404


class TestHistoryAndRatings:
    def create(self, world):
        job = submit(world, kind="playlist", prompt="x")
        world.run_all()
        return world.client.get(f"/api/jobs/{job['id']}").json()["result"]["outcome"][
            "id"
        ]

    def test_history_lists_real_creations(self, world):
        self.create(world)
        items = world.client.get("/api/history").json()["items"]
        assert [i["name"] for i in items] == ["Mix"]
        assert [t["title"] for t in items[0]["tracks"]] == ["Song 1", "Song 2"]

    def test_history_paging_is_validated(self, world):
        assert world.client.get("/api/history?limit=0").status_code == 422
        assert world.client.get("/api/history?limit=500").status_code == 422

    def test_rate_a_track_from_the_history_and_change_your_mind(self, world):
        sid = self.create(world)
        rate = lambda rating: world.client.put(  # noqa: E731
            "/api/ratings",
            json={"suggestion_id": sid, "uri": "spotify:track:1", "rating": rating},
        )
        assert rate("like").status_code == 204
        assert [
            r["title"] for r in world.client.get("/api/ratings").json()["like"]
        ] == ["Song 1"]
        assert rate("dislike").status_code == 204
        data = world.client.get("/api/ratings").json()
        assert data["like"] == [] and [r["title"] for r in data["dislike"]] == [
            "Song 1"
        ]
        assert rate(None).status_code == 204
        assert world.client.get("/api/ratings").json() == {"like": [], "dislike": []}

    def test_change_a_rating_from_the_tab_by_song_key(self, world):
        sid = self.create(world)
        world.client.put(
            "/api/ratings",
            json={"suggestion_id": sid, "uri": "spotify:track:2", "rating": "like"},
        )
        key = world.client.get("/api/ratings").json()["like"][0]["song_key"]
        assert (
            world.client.put(
                "/api/ratings", json={"song_key": key, "rating": "dislike"}
            ).status_code
            == 204
        )
        assert world.client.get("/api/ratings").json()["dislike"][0]["song_key"] == key
        assert (
            world.client.put(
                "/api/ratings", json={"song_key": key, "rating": None}
            ).status_code
            == 204
        )
        assert world.client.get("/api/ratings").json() == {"like": [], "dislike": []}

    def test_rating_something_unknown_is_a_404(self, world):
        sid = self.create(world)
        missing = {"suggestion_id": sid, "uri": "spotify:track:nope", "rating": "like"}
        assert world.client.put("/api/ratings", json=missing).status_code == 404
        assert (
            world.client.put(
                "/api/ratings", json={"song_key": "x|y", "rating": "like"}
            ).status_code
            == 404
        )

    def test_a_rating_must_identify_a_song_and_be_valid(self, world):
        assert (
            world.client.put("/api/ratings", json={"rating": "like"}).status_code == 422
        )
        bad = {"suggestion_id": 1, "uri": "u", "rating": "love"}
        assert world.client.put("/api/ratings", json=bad).status_code == 422


class TestEnvironment:
    def test_devices(self, world):
        body = world.client.get("/api/devices").json()
        assert body["error"] is None
        assert body["devices"][0]["name"] == "Kitchen"

    def test_devices_degrade_to_an_empty_list_with_the_reason(self, tmp_path):
        store = Store(tmp_path / "x.db")
        queue = JobQueue(lambda job, progress: {}, autostart=False)
        client = TestClient(
            create_app(FakeAuralis(store), store, FakeSpotify(broken=True), queue=queue)
        )
        body = client.get("/api/devices").json()
        assert body["devices"] == [] and "unreachable" in body["error"]

    def test_now_reports_city_time_zone_and_weather(self, world):
        from web.demo import DemoWeather

        world.auralis.weather = DemoWeather()
        body = world.client.get("/api/now").json()
        assert body["available"] is True
        assert (body["city"], body["country"]) == ("Baden-Baden", "DE")
        assert body["timezone"] == "Europe/Berlin"
        assert body["temperature"] == 17 and body["feels_like"] == 16
        assert body["condition"] == "Clouds" and body["description"] == "broken clouds"

    def test_now_is_unavailable_without_weather(self, world):
        assert world.client.get("/api/now").json() == {"available": False}
        world.auralis.weather = type("Down", (), {"conditions": lambda self: None})()
        assert world.client.get("/api/now").json() == {"available": False}

    def test_health(self, world):
        submit(world, kind="song")
        assert world.client.get("/api/health").json() == {
            "spotify": "ok",
            "running": False,
            "queued": 1,
        }

    def test_health_when_logged_out(self, tmp_path):
        store = Store(tmp_path / "x.db")
        queue = JobQueue(lambda job, progress: {}, autostart=False)
        client = TestClient(
            create_app(FakeAuralis(store), store, FakeSpotify(broken=True), queue=queue)
        )
        assert client.get("/api/health").json()["spotify"] == "login"


class TestStaticFiles:
    def test_the_page_and_its_assets_are_served(self, world):
        page = world.client.get("/")
        assert page.status_code == 200 and "<title>Auralis</title>" in page.text
        assert page.headers["cache-control"] == "no-cache"
        for path in ("/static/app.js", "/static/app.css", "/static/fonts/outfit.woff2"):
            assert world.client.get(path).status_code == 200

    def test_the_page_loads_nothing_from_other_hosts(self, world):
        text = "".join(
            world.client.get(path).text
            for path in ("/", "/static/app.css", "/static/app.js")
        )
        # The SVG namespace is an identifier, and open.spotify.com is the "Open in
        # Spotify" link the user clicks; neither is something the page loads.
        text = text.replace("http://www.w3.org/2000/svg", "")
        text = text.replace("https://open.spotify.com/track/", "")
        assert "googleapis" not in text and "cdn." not in text
        assert "http://" not in text and "https://" not in text


class TestDj:
    def test_unavailable_without_a_dj(self, world):
        assert world.client.get("/api/dj").json() == {"available": False}
        assert world.client.put("/api/dj", json={"enabled": True}).status_code == 404

    def test_turn_on_and_change_the_interval(self, world):
        from web.dj import Dj

        world.client.app.state.dj = Dj(object(), world.queue, world.store)
        assert world.client.get("/api/dj").json()["enabled"] is False
        body = world.client.put("/api/dj", json={"enabled": True, "minutes": 45}).json()
        assert body["enabled"] is True and body["minutes"] == 45
        assert world.client.get("/api/dj").json()["minutes"] == 45

    def test_a_silly_interval_is_refused(self, world):
        from web.dj import Dj

        world.client.app.state.dj = Dj(object(), world.queue, world.store)
        response = world.client.put("/api/dj", json={"minutes": 3})
        assert response.status_code == 422 and "minutes" in response.json()["detail"]
