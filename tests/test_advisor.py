import json

import pytest

from agent.advisor import AdvisorError, ClaudeAdvisor

SCHEMA = {"type": "object", "properties": {"song": {"type": "string"}}}


def envelope(**fields):
    return json.dumps({"is_error": False, **fields})


class FakeRun:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, args, stdin):
        self.calls.append((args, stdin))
        return self.outputs.pop(0)


def make_advisor(run, **kwargs):
    return ClaudeAdvisor(run=run, sleep=lambda seconds: None, **kwargs)


class TestClaudeAdvisor:
    def test_returns_structured_output(self):
        run = FakeRun(envelope(structured_output={"song": "Opalite"}))
        result = make_advisor(run).advise("system", "user", SCHEMA)
        assert result == {"song": "Opalite"}

    def test_falls_back_to_json_result(self):
        run = FakeRun(envelope(result='{"song": "Opalite"}'))
        assert make_advisor(run).advise("s", "u", SCHEMA) == {"song": "Opalite"}

    def test_sends_prompt_on_stdin_with_no_tools_and_no_persistence(self):
        run = FakeRun(envelope(structured_output={}))
        make_advisor(run, model="claude-sonnet-5-5").advise("sys", "the prompt", SCHEMA)
        args, stdin = run.calls[0]
        assert stdin == "the prompt"
        assert args[args.index("--model") + 1] == "claude-sonnet-5-5"
        assert args[args.index("--system-prompt") + 1] == "sys"
        assert json.loads(args[args.index("--json-schema") + 1]) == SCHEMA
        assert args[args.index("--tools") + 1] == ""
        assert "--no-session-persistence" in args
        assert "the prompt" not in args

    def test_retries_when_oauth_refresh_collides(self):
        refresh = envelope(is_error=True, result="Failed to refresh OAuth token")
        run = FakeRun(refresh, envelope(structured_output={"song": "x"}))
        assert make_advisor(run).advise("s", "u", SCHEMA) == {"song": "x"}
        assert len(run.calls) == 2

    def test_gives_up_after_max_attempts(self):
        refresh = envelope(is_error=True, result="Failed to refresh OAuth token")
        run = FakeRun(refresh, refresh)
        with pytest.raises(AdvisorError, match="refresh"):
            make_advisor(run, max_attempts=2).advise("s", "u", SCHEMA)
        assert len(run.calls) == 2

    def test_does_not_retry_other_errors(self):
        run = FakeRun(envelope(is_error=True, result="Invalid API key"))
        with pytest.raises(AdvisorError, match="Invalid API key"):
            make_advisor(run).advise("s", "u", SCHEMA)
        assert len(run.calls) == 1

    def test_rejects_non_json_output(self):
        with pytest.raises(AdvisorError, match="not JSON"):
            make_advisor(FakeRun("oops")).advise("s", "u", SCHEMA)

    def test_rejects_answer_without_structured_output(self):
        run = FakeRun(envelope(result="just some prose"))
        with pytest.raises(AdvisorError, match="no structured output"):
            make_advisor(run).advise("s", "u", SCHEMA)

    def test_config_dir_isolates_the_login(self, tmp_path):
        advisor = ClaudeAdvisor(config_dir=str(tmp_path))
        assert advisor.run is not None
