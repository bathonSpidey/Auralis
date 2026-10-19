"""The Auralis web service: a small JSON API plus the single-page UI."""

from pathlib import Path
from typing import Callable, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from agent.depth import Depth
from agent.schemas import PlaylistOutcome, SongOutcome
from web.jobs import Job, JobQueue, QueueFull

STATIC_DIR = Path(__file__).parent / "static"


class JobRequest(BaseModel):
    kind: Literal["playlist", "song"]
    prompt: str = Field(default="", max_length=600)
    depth: Optional[Depth] = None
    device_id: Optional[str] = None
    preview: bool = False

    @model_validator(mode="after")
    def playlist_needs_a_prompt(self):
        self.prompt = self.prompt.strip()
        if self.kind == "playlist" and not self.prompt:
            raise ValueError("Describe the playlist you want")
        return self


class RatingRequest(BaseModel):
    """Rate a track from the history (suggestion_id + uri), or change a song
    already on the likes/dislikes tab (song_key). rating=None makes it neutral."""

    rating: Optional[Literal["like", "dislike"]] = None
    suggestion_id: Optional[int] = None
    uri: Optional[str] = None
    song_key: Optional[str] = None

    @model_validator(mode="after")
    def identify_the_song(self):
        by_history = self.suggestion_id is not None and self.uri
        if not by_history and not self.song_key:
            raise ValueError("Give suggestion_id and uri, or song_key")
        return self


def make_runner(auralis, queue_get: Callable[[str], Optional[Job]]):
    def run(job: Job, progress) -> dict:
        depth = Depth(job.depth)
        if job.kind == "playlist":
            outcome = auralis.playlist_generator(
                job.prompt,
                depth=depth,
                dry_run=job.preview,
                device_id=job.device_id,
                source=job.source,
                progress=progress,
            )
        elif job.kind == "song":
            outcome = auralis.song_of_the_moment_suggestion(
                depth=depth,
                dry_run=job.preview,
                device_id=job.device_id,
                source=job.source,
                progress=progress,
            )
        else:  # commit: turn a finished preview into the real thing
            parent = queue_get(job.parent)
            progress("create")
            if parent.kind == "playlist":
                outcome = auralis.commit_playlist(
                    PlaylistOutcome.model_validate(parent.result["outcome"]),
                    parent.prompt,
                    depth,
                    job.device_id,
                    job.source,
                )
            else:
                outcome = auralis.commit_song(
                    SongOutcome.model_validate(parent.result["outcome"]),
                    depth,
                    job.device_id,
                    job.source,
                )
            return {"kind": parent.kind, "outcome": outcome.model_dump(mode="json")}
        return {"kind": job.kind, "outcome": outcome.model_dump(mode="json")}

    return run


def create_app(
    auralis, store, spotify, queue: Optional[JobQueue] = None, lifespan=None
) -> FastAPI:
    app = FastAPI(title="Auralis", docs_url=None, redoc_url=None, lifespan=lifespan)
    holder: Dict[str, JobQueue] = {}
    queue = queue or JobQueue(make_runner(auralis, lambda i: holder["q"].get(i)))
    holder["q"] = queue
    app.state.queue = queue

    # ── pages ───────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(
            STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"}
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ── jobs ────────────────────────────────────────────────────────────
    @app.post("/api/jobs", status_code=202)
    def create_job(request: JobRequest):
        depth = request.depth or (
            Depth.AUTO if request.kind == "playlist" else Depth.QUICK
        )
        try:
            job = queue.submit(
                request.kind,
                prompt=request.prompt,
                depth=depth.value,
                device_id=request.device_id or None,
                preview=request.preview,
            )
        except QueueFull as e:
            raise HTTPException(429, str(e))
        return queue.snapshot(job.id)

    @app.get("/api/jobs")
    def list_jobs():
        return {"jobs": queue.recent()}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = queue.snapshot(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job")
        return job

    @app.post("/api/jobs/{job_id}/create", status_code=202)
    def create_from_preview(job_id: str, device_id: Optional[str] = None):
        try:
            parent = queue.claim_commit(job_id)
        except KeyError:
            raise HTTPException(404, "Unknown job")
        except ValueError as e:
            raise HTTPException(409, str(e))
        try:
            job = queue.submit(
                "commit",
                prompt=parent.prompt,
                depth=parent.depth,
                device_id=device_id or parent.device_id,
                parent=parent.id,
            )
        except QueueFull as e:
            queue.release_commit(job_id)
            raise HTTPException(429, str(e))
        return queue.snapshot(job.id)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def discard_job(job_id: str):
        if not queue.discard(job_id):
            raise HTTPException(409, "A running job cannot be removed")

    # ── history and taste ───────────────────────────────────────────────
    @app.get("/api/history")
    def history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        return {"items": store.history(limit=limit, offset=offset)}

    @app.get("/api/ratings")
    def ratings():
        return {"like": store.ratings("like"), "dislike": store.ratings("dislike")}

    @app.put("/api/ratings", status_code=204)
    def rate(request: RatingRequest):
        try:
            if request.song_key:
                store.change_rating(request.song_key, request.rating)
            else:
                store.rate_track(request.suggestion_id, request.uri, request.rating)
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'\""))

    # ── environment ─────────────────────────────────────────────────────
    @app.get("/api/devices")
    def devices():
        try:
            found = [d.model_dump() for d in spotify.devices()]
            return {"devices": found, "error": None}
        except Exception as e:  # the page still works without the list
            return JSONResponse({"devices": [], "error": str(e)[:200]})

    @app.get("/api/health")
    def health():
        jobs = queue.recent()
        return {
            "spotify": _spotify_state(spotify),
            "running": any(j["status"] == "running" for j in jobs),
            "queued": sum(1 for j in jobs if j["status"] == "queued"),
        }

    return app


def _spotify_state(spotify) -> str:
    """'ok' when logged in. Cheap: reads the token file, never calls Spotify."""
    try:
        return "ok" if spotify.logged_in() else "login"
    except Exception:
        return "error"
