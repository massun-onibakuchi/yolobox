#!/usr/bin/env python3
"""Devcontainer post-create bootstrap.

Where: `.devcontainer/post_install.py`
What: Applies idempotent user-scoped setup after the container is created.
Why: Keeps mutable tool installs and local config out of the base image layer.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

FISH_CONFIG = """\
# default fish config for the devcontainer
set -g __fish_git_prompt_showdirtystate 0
set -g __fish_git_prompt_showuntrackedfiles 0
set -g __fish_git_prompt_showupstream none

function fish_greeting
  echo "banteg/agents · autonomous coding sandbox"
end

function fish_prompt
  set_color cyan
  echo -n (prompt_pwd)
  set_color normal
  fish_vcs_prompt
  echo -n " > "
end

# git aliases
alias ga='git add'
alias gd='git diff'
alias gs='git status'
alias gp='git push'
alias gl='git pull'
alias gb='git branch'
alias gco='git checkout'
alias gsc='git switch -c'
alias gci='git commit'
"""

TMUX_CONFIG = """\
set -g default-terminal "tmux-256color"
set -g focus-events on
set -sg escape-time 10
set -g mouse on
set -g history-limit 200000
set -g renumber-windows on
setw -g mode-keys vi

# Keep new panes/windows in the same cwd
bind c new-window -c "#{pane_current_path}"
bind | split-window -h -c "#{pane_current_path}"
bind - split-window -v -c "#{pane_current_path}"
unbind '"'
unbind %

# Reload config
bind r source-file ~/.tmux.conf \\; display-message "tmux.conf reloaded"

# Terminal features
set -as terminal-features ",xterm-ghostty:RGB"
set -as terminal-features ",xterm*:RGB"
set -ga terminal-overrides ",xterm*:colors=256"
set -ga terminal-overrides '*:Ss=\\E[%p1%d q:Se=\\E[ q'
"""


def log(message: str) -> None:
    print(f"post-install: {message}", file=sys.stderr)


def run_git(
    args: list[str], cwd: Path, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def run_sudo(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sudo", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def run_command(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
    )


def resolve_workspace() -> Path:
    env_workspace = os.environ.get("WORKSPACE_FOLDER")
    if env_workspace:
        workspace = Path(env_workspace)
    else:
        workspace = Path("/workspace")
    if workspace.exists():
        return workspace
    return Path.cwd()


def is_git_repo(cwd: Path) -> bool:
    result = run_git(["rev-parse", "--is-inside-work-tree"], cwd)
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_global_gitignore(workspace: Path) -> None:
    result = run_git(["config", "--global", "--path", "core.excludesfile"], workspace)
    if result.returncode != 0:
        log("no global core.excludesfile configured")
        return

    raw_path = result.stdout.strip()
    if not raw_path:
        log("no global core.excludesfile configured")
        return

    excludes_path = Path(raw_path).expanduser()
    if not excludes_path.is_absolute():
        excludes_path = (Path.home() / excludes_path).resolve()

    if excludes_path.exists():
        log(f"global core.excludesfile exists at {excludes_path}")
        return

    source = workspace / ".devcontainer" / ".gitignore_global"
    if not source.exists():
        log(
            f"global core.excludesfile missing at {excludes_path} and no template copy found"
        )
        return

    excludes_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, excludes_path)
    log(f"copied gitignore to {excludes_path}")


def ensure_git_worktree_relative_paths() -> None:
    result = run_command(
        ["git", "config", "--global", "--get", "worktree.useRelativePaths"]
    )
    if result.returncode == 0 and result.stdout.strip():
        log("git worktree.useRelativePaths already configured")
        return
    log(
        "git worktree.useRelativePaths not set; leaving read-only gitconfig untouched"
    )


def ensure_codex_config() -> None:
    codex_dir = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    codex_dir.mkdir(parents=True, exist_ok=True)
    codex_config = codex_dir / "config.toml"
    if codex_config.exists():
        log(f"skipping codex config (already exists at {codex_config})")
        return

    codex_config.write_text(
        'approval_policy = "never"\nsandbox_mode = "danger-full-access"\n',
        encoding="utf-8",
    )
    log(f"wrote default codex config to {codex_config}")


def ensure_claude_config() -> None:
    claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    claude_dir.mkdir(parents=True, exist_ok=True)
    claude_config = claude_dir / "settings.json"
    if claude_config.exists():
        log(f"skipping claude settings (already exists at {claude_config})")
        return

    data = {"permissions": {"defaultMode": "bypassPermissions"}}
    claude_config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    log(f"wrote default claude settings to {claude_config}")


def ensure_fish_config() -> None:
    fish_config_dir = (
        Path(
            os.environ.get(
                "XDG_CONFIG_HOME",
                str(Path.home() / ".config"),
            )
        )
        / "fish"
    )
    fish_config_dir.mkdir(parents=True, exist_ok=True)
    fish_config = fish_config_dir / "config.fish"
    if fish_config.exists():
        existing = fish_config.read_text(encoding="utf-8")
        if existing.lstrip().startswith("# default fish config for the devcontainer"):
            fish_config.write_text(FISH_CONFIG, encoding="utf-8")
            log(f"updated default fish config at {fish_config}")
            return
        log(f"skipping fish config (already exists at {fish_config})")
        return

    fish_config.write_text(FISH_CONFIG, encoding="utf-8")
    log(f"wrote default fish config to {fish_config}")


def ensure_fish_history() -> None:
    history_volume = Path("/commandhistory")
    history_volume.mkdir(parents=True, exist_ok=True)
    target = history_volume / ".fish_history"

    fish_history = Path.home() / ".local" / "share" / "fish" / "fish_history"
    fish_history.parent.mkdir(parents=True, exist_ok=True)

    if fish_history.is_symlink():
        if fish_history.resolve() == target:
            return
        fish_history.unlink()
        fish_history.symlink_to(target)
        log(f"updated fish history symlink at {fish_history}")
        return

    if fish_history.exists():
        if not target.exists():
            fish_history.replace(target)
            log(f"moved fish history to {target}")
        else:
            log(f"existing fish history left at {fish_history}")
            return

    fish_history.symlink_to(target)
    log(f"linked fish history to {target}")


def has_command(command: str) -> bool:
    return shutil.which(command) is not None


def ensure_path_entry(path: Path) -> None:
    if not path.exists():
        return

    path_str = str(path)
    current_path = os.environ.get("PATH", "")
    entries = current_path.split(os.pathsep) if current_path else []
    if path_str in entries:
        return

    os.environ["PATH"] = (
        f"{path_str}{os.pathsep}{current_path}" if current_path else path_str
    )


def ensure_worktrunk_installed() -> None:
    cargo_bin = Path.home() / ".cargo" / "bin"
    ensure_path_entry(cargo_bin)

    if has_command("wt"):
        log("worktrunk already installed")
        return

    if not has_command("cargo"):
        log("cargo not found; installing rustup toolchain for worktrunk")
        rustup = run_command(
            ["bash", "-lc", "curl https://sh.rustup.rs -sSf | sh -s -- -y"]
        )
        if rustup.returncode != 0:
            log(f"failed to install rustup: {rustup.stderr.strip()}")
            return
        ensure_path_entry(cargo_bin)

    cargo_install = run_command(
        ["bash", "-lc", 'source "$HOME/.cargo/env" && cargo install worktrunk']
    )
    if cargo_install.returncode != 0:
        log(f"failed to install worktrunk with cargo: {cargo_install.stderr.strip()}")
        return
    ensure_path_entry(cargo_bin)
    log("installed worktrunk with cargo")


def ensure_worktrunk_config() -> None:
    config_dir = Path.home() / ".config" / "worktrunk"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    desired_line = 'worktree-path = ".worktrees/{{ branch | sanitize }}"'

    existing_lines: list[str] = []
    if config_path.exists():
        existing_lines = config_path.read_text(encoding="utf-8").splitlines()

    updated_lines: list[str] = []
    replaced = False
    for line in existing_lines:
        if line.strip().startswith("worktree-path"):
            if not replaced:
                updated_lines.append(desired_line)
                replaced = True
            continue
        updated_lines.append(line)

    if not replaced:
        if updated_lines and updated_lines[-1].strip() != "":
            updated_lines.append("")
        updated_lines.append(desired_line)

    rendered = "\n".join(updated_lines).rstrip() + "\n"
    if config_path.exists() and config_path.read_text(encoding="utf-8") == rendered:
        log(f"worktrunk config already up to date at {config_path}")
        return

    config_path.write_text(rendered, encoding="utf-8")
    log(f"updated worktrunk config at {config_path}")


def ensure_worktrunk_shell_integration() -> None:
    if not has_command("wt"):
        log("skipping wt shell install (worktrunk is not available)")
        return

    shell_install = run_command(["wt", "config", "shell", "install", "--yes"])
    if shell_install.returncode != 0:
        log(f"wt shell install failed: {shell_install.stderr.strip()}")
        return
    log("installed worktrunk shell integration")


def ensure_dir_ownership(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        stat = path.stat()
    except OSError as exc:
        log(f"unable to stat {path}: {exc}")
        return

    uid = os.getuid()
    gid = os.getgid()
    if stat.st_uid == uid and stat.st_gid == gid:
        return

    result = run_sudo(["chown", "-R", f"{uid}:{gid}", str(path)])
    if result.returncode != 0:
        log(f"failed to chown {path}: {result.stderr.strip()}")
        return
    log(f"fixed ownership for {path}")


def install_tmux_config() -> None:
    tmux_dest = Path.home() / ".tmux.conf"
    if tmux_dest.exists():
        log(f"skipping tmux config (already exists at {tmux_dest})")
        return

    tmux_dest.write_text(TMUX_CONFIG, encoding="utf-8")
    log(f"installed tmux config to {tmux_dest}")


def main() -> None:
    workspace = resolve_workspace()
    if not is_git_repo(workspace):
        log(f"skipping git repo checks (no repo at {workspace})")

    install_tmux_config()
    ensure_dir_ownership(Path("/commandhistory"))
    ensure_dir_ownership(Path.home() / ".claude")
    ensure_dir_ownership(Path.home() / ".codex")
    ensure_dir_ownership(Path.home() / ".config" / "gh")
    ensure_fish_history()
    ensure_global_gitignore(workspace)
    ensure_git_worktree_relative_paths()
    ensure_codex_config()
    ensure_claude_config()
    ensure_fish_config()
    ensure_worktrunk_installed()
    ensure_worktrunk_config()
    ensure_worktrunk_shell_integration()
    log("configured defaults for container use")


if __name__ == "__main__":
    main()
