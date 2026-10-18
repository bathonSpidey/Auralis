"""How hard Claude may research a request.

Depth decides what Claude is *allowed* to do (is web search even available?)
and how much it may spend, not just what the prompt suggests.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class Depth(str, Enum):
    QUICK = "quick"
    AUTO = "auto"
    DEEP = "deep"


@dataclass(frozen=True)
class DepthPlan:
    # ToolSearch is how Claude Code loads WebSearch on demand.
    builtin_tools: Tuple[str, ...]
    guidance: str
    budget_usd: float


PLANS = {
    Depth.QUICK: DepthPlan(
        builtin_tools=(),
        guidance=(
            "Do not use the web. Work only from the listener profile and "
            "Spotify lookups."
        ),
        budget_usd=2.0,
    ),
    Depth.AUTO: DepthPlan(
        builtin_tools=("WebSearch", "ToolSearch"),
        guidance=(
            "The profile and Spotify lookups should usually be enough. Use web "
            "search only if the request needs knowledge you lack (a specific "
            "scene, era or region, new releases, or what is trending), keep it "
            "to at most 3 searches, and skip it entirely otherwise."
        ),
        budget_usd=4.0,
    ),
    Depth.DEEP: DepthPlan(
        builtin_tools=("WebSearch", "ToolSearch"),
        guidance=(
            "Research thoroughly. Use web search generously (up to about 15 "
            "searches): recent releases, scene guides, critics' lists, regional "
            "charts and 'songs like X' recommendations, and cross-check your "
            "candidates. Prioritise fresh finds beyond the obvious ones."
        ),
        budget_usd=10.0,
    ),
}
