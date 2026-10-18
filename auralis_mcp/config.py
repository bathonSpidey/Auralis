"""The --mcp-config that makes Claude Code start the Auralis server."""

import os
import sys
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_NAME = "auralis"

# Variables the server needs. Claude Code gives MCP servers a trimmed
# environment, so these are passed explicitly. No secrets are involved: the
# Spotify login lives in the token file under AURALIS_DATA_DIR.
_PASSTHROUGH = (
    "SPOTIFY_CLIENT_ID",
    "SPOTIPY_CLIENT_ID",
    "SPOTIFY_REDIRECT_URI",
    "AURALIS_DATA_DIR",
    "SYSTEMROOT",
    "USERPROFILE",
    "HOME",
)


def mcp_config(run_dir: Path, stage: str, python: str = sys.executable) -> Dict:
    env = {key: os.environ[key] for key in _PASSTHROUGH if key in os.environ}
    env["AURALIS_RUN_DIR"] = str(run_dir)
    env["AURALIS_STAGE"] = stage
    env["PYTHONPATH"] = str(REPO_ROOT)
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": python,
                "args": ["-m", "auralis_mcp"],
                "env": env,
            }
        }
    }


def allowed_tools() -> str:
    """Permission rule covering every tool of the Auralis server."""
    return f"mcp__{SERVER_NAME}"
