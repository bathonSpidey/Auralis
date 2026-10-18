"""Calls Claude Code headlessly as the music advisor. The subprocess runner is
injected, so tests never invoke the CLI.

No tools are granted and nothing is persisted: the advisor reasons over the
context it is given and answers in the requested JSON schema. Executing the
answer against Spotify stays in deterministic code.
"""

import json
import os
import subprocess  # only ever runs the claude binary with a fixed arg list  # nosec B404
import tempfile
import time
from typing import Callable, Optional, Protocol, Sequence

DEFAULT_MODEL = "claude-sonnet-5-5"

RunFn = Callable[[list, str], str]

_TRANSIENT_MARKERS = ("refresh", "overloaded")


class AdvisorError(RuntimeError):
    pass


class Advisor(Protocol):
    def advise(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        *,
        mcp_config: Optional[dict] = None,
        allowed_tools: Sequence[str] = (),
        builtin_tools: Sequence[str] = (),
        max_budget_usd: Optional[float] = None,
    ) -> dict: ...


def subprocess_runner(env=None, cwd=None, timeout=1800) -> RunFn:
    def run(args: list, stdin: str) -> str:
        try:
            proc = subprocess.run(  # fixed arg list, no shell  # nosec B603
                args,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                cwd=cwd,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as e:
            raise AdvisorError(f"claude binary not found: {args[0]}") from e
        except subprocess.TimeoutExpired as e:
            raise AdvisorError(f"claude timed out after {timeout}s") from e
        if not proc.stdout.strip():
            raise AdvisorError(
                f"claude returned no output: {proc.stderr.strip()[:500]}"
            )
        return proc.stdout

    return run


class ClaudeAdvisor:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        claude_binary: str = "claude",
        config_dir: Optional[str] = None,
        timeout: int = 1800,
        max_attempts: int = 3,
        retry_delay: float = 30,
        run: Optional[RunFn] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.claude_binary = claude_binary
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.sleep = sleep
        env = os.environ.copy()
        if config_dir:
            # A separate config dir means a separate login, so Auralis never
            # races other Claude Code users for the same OAuth token refresh.
            env["CLAUDE_CONFIG_DIR"] = config_dir
        self.run = run or subprocess_runner(
            env=env, cwd=tempfile.gettempdir(), timeout=timeout
        )

    def advise(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
        *,
        mcp_config: Optional[dict] = None,
        allowed_tools: Sequence[str] = (),
        builtin_tools: Sequence[str] = (),
        max_budget_usd: Optional[float] = None,
    ) -> dict:
        """Ask Claude for an answer in `schema`.

        By default Claude has no tools. `builtin_tools` (e.g. WebSearch) and an
        `mcp_config` server can be enabled per call; `allowed_tools` are the
        permission rules that let them run unattended (e.g. "WebSearch",
        "mcp__auralis").
        """
        args = [
            self.claude_binary,
            "-p",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            "--system-prompt",
            system_prompt,
            "--tools",
            ",".join(builtin_tools),
            "--no-session-persistence",
        ]
        if mcp_config:
            args += ["--mcp-config", json.dumps(mcp_config), "--strict-mcp-config"]
        if allowed_tools:
            args += ["--allowedTools", ",".join(allowed_tools)]
        if max_budget_usd is not None:
            args += ["--max-budget-usd", str(max_budget_usd)]
        for attempt in range(1, self.max_attempts + 1):
            envelope = self._parse_envelope(self.run(args, user_prompt))
            if not envelope.get("is_error"):
                return self._structured_output(envelope)
            message = str(envelope.get("result", ""))
            transient = any(marker in message.lower() for marker in _TRANSIENT_MARKERS)
            if not transient or attempt == self.max_attempts:
                raise AdvisorError(f"claude failed: {message[:500]}")
            self.sleep(self.retry_delay * attempt)

    @staticmethod
    def _parse_envelope(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise AdvisorError(f"claude output was not JSON: {raw[:500]}") from e

    @staticmethod
    def _structured_output(envelope: dict) -> dict:
        structured = envelope.get("structured_output")
        if isinstance(structured, dict):
            return structured
        try:
            parsed = json.loads(envelope.get("result", ""))
        except (TypeError, json.JSONDecodeError) as e:
            raise AdvisorError("claude returned no structured output") from e
        if not isinstance(parsed, dict):
            raise AdvisorError("claude returned no structured output")
        return parsed
