"""Where: CLI tests. What: verify config and task lifecycle commands. Why: keep the user-facing contract reliable."""

from pathlib import Path
import sqlite3

import pytest

from scheduled_agent_runner import cli
from scheduled_agent_runner.config import load_config
from scheduled_agent_runner.cli import main
from scheduled_agent_runner.db import connect, enqueue_run, utc_now
from scheduled_agent_runner.runner import RunResult


CONFIG_TEMPLATE = """
[paths]
state_db = "state.sqlite3"
logs_dir = "logs"

[codex]
binary = "codex"
default_model = "gpt-5.4"
allowed_models = ["gpt-5.4", "gpt-5.4-mini"]

[scheduler]
timezone = "UTC"
poll_seconds = 1
error_backoff_seconds = 2

[telegram]
bot_token = "replace-me"

[notifications]
send_on_start = true
send_on_success = true
send_on_failure = true
summary_chars = 1200
""".strip()


def test_schedule_and_list_task(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(
        [
            "--config",
            str(config_path),
            "schedule",
            "--task",
            "nightly-review",
            "--when",
            "every 30m",
            "--prompt",
            "Review the repository.",
            "--chat-id",
            "12345",
        ]
    )
    assert exit_code == 0

    exit_code = main(["--config", str(config_path), "status"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "nightly-review" in output
    assert "session_mode=fresh" in output
    assert "enabled=True" in output


def test_set_default_model(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    exit_code = main(["--config", str(config_path), "config", "set-default-model", "gpt-5.4-mini"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "gpt-5.4-mini" in output
    assert "default_model = \"gpt-5.4-mini\"" in config_path.read_text(encoding="utf-8")


def test_set_default_model_preserves_env_secret_reference(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, bot_token="env:TG_BOT_TOKEN")
    monkeypatch.setenv("TG_BOT_TOKEN", "secret-token")

    config = load_config(config_path)
    assert config.telegram.bot_token == "secret-token"

    exit_code = main(["--config", str(config_path), "config", "set-default-model", "gpt-5.4-mini"])

    assert exit_code == 0
    saved_config = config_path.read_text(encoding="utf-8")
    assert 'bot_token = "env:TG_BOT_TOKEN"' in saved_config
    assert "secret-token" not in saved_config


def test_default_config_is_discovered_from_parent_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path)
    nested_dir = tmp_path / "nested" / "workspace"
    nested_dir.mkdir(parents=True)
    monkeypatch.chdir(nested_dir)

    exit_code = main(["config", "get-default-model"])

    assert exit_code == 0
    assert "gpt-5.4" in capsys.readouterr().out


def test_default_config_can_be_set_with_env_var(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path / ".automation")
    monkeypatch.setenv("SCHEDULED_AGENT_RUNNER_CONFIG", str(config_path))

    exit_code = main(["config", "get-default-model"])

    assert exit_code == 0
    assert "gpt-5.4" in capsys.readouterr().out


def test_pause_resume_and_edit_task(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    main(
        [
            "--config",
            str(config_path),
            "schedule",
            "--task",
            "editable-task",
            "--when",
            "every 30m",
            "--prompt",
            "old prompt",
            "--model",
            "gpt-5.4",
            "--chat-id",
            "12345",
        ]
    )

    assert main(["--config", str(config_path), "pause", "--task", "editable-task"]) == 0
    assert main(["--config", str(config_path), "status"]) == 0
    assert "enabled=False" in capsys.readouterr().out

    assert (
        main(
            [
                "--config",
                str(config_path),
                "edit",
                "--task",
                "editable-task",
                "--prompt",
                "new prompt",
                "--model",
                "gpt-5.4-mini",
                "--session-mode",
                "resume",
                "--chat-id",
                "67890",
            ]
        )
        == 0
    )
    row = _task_row(config_path, "editable-task")
    assert row["prompt"] == "new prompt"
    assert row["model"] == "gpt-5.4-mini"
    assert row["session_mode"] == "resume"
    assert row["chat_id"] == "67890"
    assert row["session_id"] is None

    assert main(["--config", str(config_path), "resume", "--task", "editable-task"]) == 0
    row = _task_row(config_path, "editable-task")
    assert row["enabled"] == 1


def test_removed_legacy_subcommands_are_rejected(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    for legacy_name in ("list", "unregister", "daemon"):
        with pytest.raises(SystemExit):
            main(["--config", str(config_path), legacy_name])


def test_one_time_task_disables_after_run(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)
    main(
        [
            "--config",
            str(config_path),
            "schedule",
            "--task",
            "say-hi-once",
            "--when",
            "in 5m",
            "--prompt",
            "say hi",
            "--model",
            "gpt-5.4-mini",
            "--chat-id",
            "0",
        ]
    )

    db_path = config_path.parent / "state.sqlite3"
    connection = connect(db_path)
    connection.execute("UPDATE tasks SET next_run_at = ?", (utc_now(),))
    connection.commit()

    def fake_run_codex_task(*args, **kwargs):
        return RunResult(
            success=True,
            exit_code=0,
            session_id="session-1",
            summary="hi",
            error_text=None,
            log_path=tmp_path / "run.log",
        )

    monkeypatch.setattr(cli, "run_codex_task", fake_run_codex_task)
    monkeypatch.setattr(cli, "send_telegram_message", lambda *args, **kwargs: None)

    exit_code = main(["--config", str(config_path), "run", "--once"])
    assert exit_code == 0

    exit_code = main(["--config", str(config_path), "status"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "say-hi-once" in output
    assert "enabled=False" in output
    assert "last_status=success" in output


def test_queued_run_is_kept_when_execution_crashes(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    main(
        [
            "--config",
            str(config_path),
            "schedule",
            "--task",
            "queued-task",
            "--when",
            "every 30m",
            "--prompt",
            "queued prompt",
            "--chat-id",
            "0",
        ]
    )
    connection = connect(config_path.parent / "state.sqlite3")
    enqueue_run(connection, "queued-task", utc_now())

    def crash_execute_task(*args, **kwargs):
        raise RuntimeError("queued execution crashed")

    monkeypatch.setattr(cli, "_execute_task", crash_execute_task)

    exit_code = main(["--config", str(config_path), "run", "--once"])

    assert exit_code == 1
    queue_count = connection.execute(
        "SELECT COUNT(*) FROM run_queue WHERE task_id = ?",
        ("queued-task",),
    ).fetchone()[0]
    assert queue_count == 1


def test_due_task_is_not_advanced_when_enqueue_crashes(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    main(
        [
            "--config",
            str(config_path),
            "schedule",
            "--task",
            "running-task",
            "--when",
            "every 30m",
            "--prompt",
            "queued prompt",
            "--chat-id",
            "0",
        ]
    )
    connection = connect(config_path.parent / "state.sqlite3")
    due_at = utc_now()
    connection.execute("UPDATE tasks SET next_run_at = ? WHERE task_id = ?", (due_at, "running-task"))
    connection.commit()

    monkeypatch.setattr(cli, "has_running_run", lambda *args, **kwargs: True)

    def crash_enqueue(*args, **kwargs):
        raise RuntimeError("enqueue crashed")

    monkeypatch.setattr(cli, "enqueue_run", crash_enqueue)

    exit_code = main(["--config", str(config_path), "run", "--once"])

    assert exit_code == 1
    row = connection.execute("SELECT next_run_at FROM tasks WHERE task_id = ?", ("running-task",)).fetchone()
    assert row["next_run_at"] == due_at


def test_enqueue_run_is_idempotent_for_same_due_time(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    main(
        [
            "--config",
            str(config_path),
            "schedule",
            "--task",
            "duplicate-queue-task",
            "--when",
            "every 30m",
            "--prompt",
            "queued prompt",
            "--chat-id",
            "0",
        ]
    )
    connection = connect(config_path.parent / "state.sqlite3")
    due_at = utc_now()

    enqueue_run(connection, "duplicate-queue-task", due_at)
    enqueue_run(connection, "duplicate-queue-task", due_at)

    queue_count = connection.execute(
        "SELECT COUNT(*) FROM run_queue WHERE task_id = ?",
        ("duplicate-queue-task",),
    ).fetchone()[0]
    assert queue_count == 1


def test_run_once_logs_unexpected_loop_error(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)

    def fail_process_due_tasks(*args, **kwargs):
        raise RuntimeError("synthetic scheduler failure")

    monkeypatch.setattr(cli, "_process_due_tasks", fail_process_due_tasks)
    exit_code = main(["--config", str(config_path), "run", "--once"])

    assert exit_code == 1
    scheduler_log = config_path.parent / "logs" / "scheduler.log"
    assert "synthetic scheduler failure" in scheduler_log.read_text(encoding="utf-8")


def test_run_loop_backs_off_and_continues_after_unexpected_error(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    calls = []
    sleeps = []

    class StopLoop(BaseException):
        pass

    def process_due_tasks_then_stop(*args, **kwargs):
        calls.append("called")
        if len(calls) == 1:
            raise RuntimeError("transient scheduler failure")
        raise StopLoop()

    monkeypatch.setattr(cli, "_process_due_tasks", process_due_tasks_then_stop)
    monkeypatch.setattr(cli, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(StopLoop):
        main(["--config", str(config_path), "run"])

    assert calls == ["called", "called"]
    assert sleeps == [2]
    scheduler_log = config_path.parent / "logs" / "scheduler.log"
    assert "transient scheduler failure" in scheduler_log.read_text(encoding="utf-8")


def test_run_loop_accepts_user_interrupt_without_retrying(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)

    def interrupt_process_due_tasks(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli, "_process_due_tasks", interrupt_process_due_tasks)

    exit_code = main(["--config", str(config_path), "run"])

    assert exit_code == 130
    assert "scheduler interrupted by user" in capsys.readouterr().err
    assert not (config_path.parent / "logs" / "scheduler.log").exists()


def test_run_loop_accepts_user_interrupt_during_sleep(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(cli, "_process_due_tasks", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    exit_code = main(["--config", str(config_path), "run"])

    assert exit_code == 130
    assert "scheduler interrupted by user" in capsys.readouterr().err
    assert not (config_path.parent / "logs" / "scheduler.log").exists()


def test_run_loop_accepts_user_interrupt_during_error_backoff(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)

    def fail_process_due_tasks(*args, **kwargs):
        raise RuntimeError("transient scheduler failure")

    monkeypatch.setattr(cli, "_process_due_tasks", fail_process_due_tasks)
    monkeypatch.setattr(cli, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    exit_code = main(["--config", str(config_path), "run"])

    assert exit_code == 130
    assert "scheduler interrupted by user" in capsys.readouterr().err
    scheduler_log = config_path.parent / "logs" / "scheduler.log"
    assert "transient scheduler failure" in scheduler_log.read_text(encoding="utf-8")


def _write_config(tmp_path: Path, bot_token: str = "replace-me") -> Path:
    config_dir = tmp_path / ".automation" / "scheduled-agent-runner"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.toml"
    config_text = CONFIG_TEMPLATE.replace('bot_token = "replace-me"', f'bot_token = "{bot_token}"')
    config_path.write_text(config_text, encoding="utf-8")
    return config_path


def _task_row(config_path: Path, task_id: str):
    connection = sqlite3.connect(config_path.parent / "state.sqlite3")
    connection.row_factory = sqlite3.Row
    return connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
