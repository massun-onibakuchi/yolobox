"""Tests for devcontainer post-create bootstrap behavior.

Where: `tests/test_post_install.py`
What: Covers repair logic for agent CLI installs.
Why: The container should recover from incomplete global npm packages.
"""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / ".devcontainer" / "post_install.py"
)
SPEC = importlib.util.spec_from_file_location("post_install", MODULE_PATH)
assert SPEC is not None
post_install = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(post_install)


def completed(
    args: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
):
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class AgentCliRepairTests(unittest.TestCase):
    def test_healthy_cli_is_not_reinstalled(self) -> None:
        calls: list[list[str]] = []

        def fake_run(args, cwd=None):
            calls.append(args)
            return completed(args, stdout="codex-cli 0.128.0\n")

        with mock.patch.object(post_install, "run_command", side_effect=fake_run):
            post_install.ensure_agent_cli("codex", "@openai/codex", "CODEX_VERSION")

        self.assertEqual(calls, [["codex", "--version"]])

    def test_broken_cli_is_reinstalled_and_verified(self) -> None:
        calls: list[list[str]] = []
        results = [
            completed(
                ["codex", "--version"],
                returncode=1,
                stderr="Invalid package config",
            ),
            completed(["npm", "install", "-g", "@openai/codex@latest"]),
            completed(["codex", "--version"], stdout="codex-cli 0.128.0\n"),
        ]

        def fake_run(args, cwd=None):
            calls.append(args)
            return results.pop(0)

        with (
            mock.patch.object(post_install, "run_command", side_effect=fake_run),
            mock.patch.object(post_install, "has_command", return_value=True),
        ):
            post_install.ensure_agent_cli("codex", "@openai/codex", "CODEX_VERSION")

        self.assertEqual(
            calls,
            [
                ["codex", "--version"],
                ["npm", "install", "-g", "@openai/codex@latest"],
                ["codex", "--version"],
            ],
        )

    def test_version_env_pins_repair_install(self) -> None:
        with mock.patch.dict(post_install.os.environ, {"CODEX_VERSION": "0.128.0"}):
            self.assertEqual(
                post_install.npm_package_spec("@openai/codex", "CODEX_VERSION"),
                "@openai/codex@0.128.0",
            )


if __name__ == "__main__":
    unittest.main()
