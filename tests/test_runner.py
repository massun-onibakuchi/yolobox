"""Where: runner tests. What: verify Codex command construction. Why: keep session-mode behavior explicit and stable."""

from scheduled_agent_runner.runner import build_command


def test_build_command_for_fresh_session() -> None:
    command = build_command(
        codex_binary="codex",
        prompt="Hello",
        model="gpt-5.4",
        session_mode="fresh",
        session_id=None,
    )
    assert command == ["codex", "exec", "--json", "--skip-git-repo-check", "-m", "gpt-5.4", "Hello"]


def test_build_command_for_resume_session() -> None:
    command = build_command(
        codex_binary="codex",
        prompt="Hello again",
        model="gpt-5.4-mini",
        session_mode="resume",
        session_id="session-123",
    )
    assert command == ["codex", "exec", "resume", "--json", "session-123", "-m", "gpt-5.4-mini", "Hello again"]

