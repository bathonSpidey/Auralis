"""Per-run scratch directories for the scout/curator hand-off.

A successful run leaves nothing behind. A failed run keeps its directory for
debugging, but only the newest few, so nothing accumulates.
"""

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

KEEP_FAILED = 10


def default_runs_dir() -> Path:
    data_dir = os.getenv("AURALIS_DATA_DIR") or Path.home() / "auralis-data"
    return Path(data_dir) / "runs"


def _prune(base: Path, keep: int) -> None:
    runs = sorted(
        (p for p in base.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in runs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


@contextmanager
def run_workspace(
    base: Optional[Path] = None, keep_failed: int = KEEP_FAILED
) -> Iterator[Path]:
    base = Path(base) if base else default_runs_dir()
    base.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=base))
    try:
        yield run_dir
    except BaseException:
        _prune(base, keep_failed)
        raise
    shutil.rmtree(run_dir, ignore_errors=True)
