from urllib.parse import parse_qs, urlparse

import pytest

from spotify.auth import (
    SCOPES,
    SpotifyAuth,
    SpotifyAuthError,
    Token,
    TokenStore,
)
from tests.spotify_fakes import FakeResponse


class FakePost:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, data=None, timeout=None):
        self.calls.append(data)
        return self.responses.pop(0)


def make_auth(tmp_path, *responses, now=1000.0):
    post = FakePost(*responses)
    store = TokenStore(tmp_path / "token.json")
    auth = SpotifyAuth("client-id", store=store, post=post, clock=lambda: now)
    return auth, store, post


def token_response(access="access", refresh=None, expires_in=3600):
    body = {"access_token": access, "expires_in": expires_in, "scope": "a b"}
    if refresh:
        body["refresh_token"] = refresh
    return FakeResponse(200, body)


class TestLogin:
    def test_authorize_url_uses_pkce_and_all_scopes(self, tmp_path):
        auth, _, _ = make_auth(tmp_path)
        session = auth.begin_login()
        query = parse_qs(urlparse(session.url).query)
        assert query["client_id"] == ["client-id"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["redirect_uri"] == ["http://127.0.0.1:8501"]
        assert query["state"] == [session.state]
        assert query["scope"] == [" ".join(SCOPES)]
        assert "client_secret" not in query

    def test_complete_login_from_redirect_url_saves_token(self, tmp_path):
        auth, store, post = make_auth(tmp_path, token_response(refresh="r1"))
        session = auth.begin_login()
        redirect = f"http://127.0.0.1:8501/?code=abc&state={session.state}"
        token = auth.complete_login(session, redirect)
        assert token.refresh_token == "r1"
        assert store.load() == token
        assert post.calls[0]["code"] == "abc"
        assert post.calls[0]["code_verifier"] == session.verifier

    def test_complete_login_accepts_a_bare_code(self, tmp_path):
        auth, _, post = make_auth(tmp_path, token_response(refresh="r1"))
        auth.complete_login(auth.begin_login(), "just-a-code")
        assert post.calls[0]["code"] == "just-a-code"

    def test_state_mismatch_is_rejected(self, tmp_path):
        auth, store, _ = make_auth(tmp_path)
        session = auth.begin_login()
        with pytest.raises(SpotifyAuthError, match="state"):
            auth.complete_login(session, "http://127.0.0.1:8501/?code=abc&state=bad")
        assert store.load() is None

    def test_denied_login_is_reported(self, tmp_path):
        auth, _, _ = make_auth(tmp_path)
        with pytest.raises(SpotifyAuthError, match="access_denied"):
            auth.complete_login(
                auth.begin_login(), "http://127.0.0.1:8501/?error=access_denied"
            )

    def test_missing_client_id(self):
        with pytest.raises(SpotifyAuthError, match="SPOTIFY_CLIENT_ID"):
            SpotifyAuth("")


class TestAccessToken:
    def test_not_logged_in(self, tmp_path):
        auth, _, _ = make_auth(tmp_path)
        with pytest.raises(SpotifyAuthError, match="spotify.login"):
            auth.access_token()

    def test_fresh_token_is_returned_without_a_request(self, tmp_path):
        auth, store, post = make_auth(tmp_path)
        store.save(Token("live", "r", expires_at=5000.0))
        assert auth.access_token() == "live"
        assert post.calls == []

    def test_expired_token_is_refreshed_and_saved(self, tmp_path):
        auth, store, post = make_auth(tmp_path, token_response(access="new"))
        store.save(Token("old", "r1", expires_at=1010.0))  # inside the margin
        assert auth.access_token() == "new"
        assert post.calls[0]["grant_type"] == "refresh_token"
        assert "client_secret" not in post.calls[0]
        saved = store.load()
        assert saved.access_token == "new"
        assert saved.refresh_token == "r1"  # not rotated, keep the old one

    def test_rotated_refresh_token_is_stored(self, tmp_path):
        auth, store, _ = make_auth(tmp_path, token_response(refresh="r2"))
        store.save(Token("old", "r1", expires_at=0))
        auth.access_token()
        assert store.load().refresh_token == "r2"

    def test_force_refresh(self, tmp_path):
        auth, store, post = make_auth(tmp_path, token_response(access="new"))
        store.save(Token("live", "r1", expires_at=9999.0))
        assert auth.access_token(force_refresh=True) == "new"
        assert len(post.calls) == 1

    def test_revoked_login_explains_how_to_recover(self, tmp_path):
        revoked = FakeResponse(
            400,
            {"error": "invalid_grant", "error_description": "Refresh token revoked"},
        )
        auth, store, _ = make_auth(tmp_path, revoked)
        store.save(Token("old", "r1", expires_at=0))
        with pytest.raises(SpotifyAuthError, match="python -m spotify.login"):
            auth.access_token()

    def test_unreadable_token_file(self, tmp_path):
        auth, store, _ = make_auth(tmp_path)
        store.path.write_text("not json")
        with pytest.raises(SpotifyAuthError, match="Unreadable"):
            auth.access_token()

    def test_store_leaves_no_temp_files(self, tmp_path):
        store = TokenStore(tmp_path / "data" / "token.json")
        store.save(Token("a", "r", 1.0))
        assert [p.name for p in (tmp_path / "data").iterdir()] == ["token.json"]
