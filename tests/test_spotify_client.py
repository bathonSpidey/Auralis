import pytest

from spotify.client import SpotifyClient, SpotifyError
from tests.spotify_fakes import FakeResponse, FakeSession, StubAuth


def make_client(routes, **kwargs):
    session = FakeSession(routes)
    sleeps = []
    client = SpotifyClient(StubAuth(), session=session, sleep=sleeps.append, **kwargs)
    return client, session, sleeps


class TestRequest:
    def test_sends_bearer_token_and_returns_json(self):
        client, session, _ = make_client(
            {("GET", "/me"): FakeResponse(200, {"id": "u"})}
        )
        assert client.get("/me") == {"id": "u"}
        assert session.calls[0]["headers"] == {"Authorization": "Bearer token"}

    def test_empty_response_is_none(self):
        client, _, _ = make_client({("PUT", "/x"): FakeResponse(204)})
        assert client.put("/x") is None

    def test_refreshes_the_token_once_on_401(self):
        routes = {
            ("GET", "/me"): [
                FakeResponse(401, {"error": {"message": "expired"}}),
                FakeResponse(200, {"id": "u"}),
            ]
        }
        client, session, _ = make_client(routes)
        assert client.get("/me") == {"id": "u"}
        assert session.calls[1]["headers"] == {"Authorization": "Bearer fresh-token"}

    def test_persistent_401_raises(self):
        client, _, _ = make_client(
            {("GET", "/me"): FakeResponse(401, {"error": {"message": "bad token"}})}
        )
        with pytest.raises(SpotifyError, match="bad token") as exc:
            client.get("/me")
        assert exc.value.status == 401

    def test_rate_limit_waits_for_retry_after(self):
        routes = {
            ("GET", "/me"): [
                FakeResponse(429, headers={"Retry-After": "3"}),
                FakeResponse(200, {"id": "u"}),
            ]
        }
        client, _, sleeps = make_client(routes)
        assert client.get("/me") == {"id": "u"}
        assert sleeps == [4.0]

    def test_quota_exceeded_with_long_wait_is_raised_not_slept(self):
        body = {"message": "Too many requests", "reason": "QUOTA_EXCEEDED"}
        client, _, sleeps = make_client(
            {("GET", "/me"): FakeResponse(429, body, {"Retry-After": "3600"})}
        )
        with pytest.raises(SpotifyError, match="QUOTA_EXCEEDED"):
            client.get("/me")
        assert sleeps == []

    def test_server_errors_are_retried_then_raised(self):
        client, session, sleeps = make_client(
            {("GET", "/me"): FakeResponse(503, {"error": {"message": "down"}})},
            max_retries=2,
        )
        with pytest.raises(SpotifyError, match="down"):
            client.get("/me")
        assert len(session.calls) == 3
        assert sleeps == [2.0, 4.0]

    def test_client_errors_are_not_retried(self):
        client, session, _ = make_client(
            {
                ("GET", "/x"): FakeResponse(
                    404, {"error": {"status": 404, "message": "Not found"}}
                )
            }
        )
        with pytest.raises(SpotifyError, match="Not found"):
            client.get("/x")
        assert len(session.calls) == 1


class TestGetAll:
    @staticmethod
    def pages(total, per_page):
        def respond(params, _):
            start = params["offset"]
            count = min(params["limit"], per_page, total - start)
            items = list(range(start, start + count))
            more = start + count < total
            return FakeResponse(200, {"items": items, "next": "more" if more else None})

        return respond

    def test_collects_across_pages(self):
        client, session, _ = make_client({("GET", "/list"): self.pages(25, 10)})
        assert client.get_all("/list", page_size=10, max_items=100) == list(range(25))
        assert [c["params"]["offset"] for c in session.calls] == [0, 10, 20]

    def test_stops_at_max_items(self):
        client, session, _ = make_client({("GET", "/list"): self.pages(100, 10)})
        assert len(client.get_all("/list", page_size=10, max_items=15)) == 15
        assert [c["params"]["limit"] for c in session.calls] == [10, 5]

    def test_pick_extracts_a_nested_paging_object(self):
        route = FakeResponse(200, {"tracks": {"items": [1, 2], "next": None}})
        client, _, _ = make_client({("GET", "/search"): route})
        items = client.get_all("/search", pick=lambda body: body["tracks"])
        assert items == [1, 2]
