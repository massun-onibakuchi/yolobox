# Yolobox

a devcontainer for running claude code and codex in yolo mode.

## Setup

### Notification

For full telegram control of agents, use [takopi](https://github.com/banteg/takopi). it bridges codex, claude code, opencode, and pi, streams progress, and supports resumable sessions so you can start a task on your phone and pick it up in the terminal later. install with `uv tool install takopi` and run it in your repo.

For simple completion notifications, use this codex `notify` [script](https://github.com/banteg/agents/tree/master) to send a telegram message at the end of each turn.

### Scheduled Agent Runner

Yolobox also includes a container-local scheduler for unattended coding-agent tasks. The first supported harness is Codex; the public command and config paths use agent-runner naming so Claude Code or other harnesses can be added later without another rename.

Edit [.automation/scheduled-agent-runner/config.toml](.automation/scheduled-agent-runner/config.toml) and set:

- `telegram.bot_token`
- `codex.default_model`
- `codex.allowed_models`
- `scheduler.timezone`

Run commands from the Yolobox repo root or a child directory. If you install the package and run it elsewhere, pass `--config /path/to/config.toml` or set `SCHEDULED_AGENT_RUNNER_CONFIG`.

```sh
uv sync --extra dev
bin/scheduled-agent-runner schedule \
  --task nightly-review \
  --when "weekdays 09:00" \
  --prompt "Review the repository and propose changes." \
  --chat-id 123456789 \
  --session-mode fresh
```

```sh
bin/scheduled-agent-runner status
bin/scheduled-agent-runner run
```

`run` is resilient by default. If an unexpected scheduler-loop error occurs, it writes the traceback to `logs/scheduler.log`, waits `scheduler.error_backoff_seconds`, and continues. User interruption with `Ctrl-C` exits cleanly with code `130` and is not retried. `run --once` logs unexpected loop errors and exits non-zero.

Manage existing tasks:

```sh
bin/scheduled-agent-runner pause --task nightly-review
bin/scheduled-agent-runner resume --task nightly-review
bin/scheduled-agent-runner edit --task nightly-review --prompt "Review only changed files." --model gpt-5.4-mini
bin/scheduled-agent-runner remove --task nightly-review
```

Use `--session-mode resume` when a task should continue the same Codex thread across runs. The default is `fresh`.

Supported schedules include one-time and recurring forms:

```text
in 5m
in 2h
every 30m
every 6h
daily 09:00
weekdays 14:30
mon,wed,fri 18:45
cron "0 9 * * 1-5"
```

`in <duration>` schedules run once and are disabled after their due run is attempted.

#### Setup Takopi

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
```

```sh
uv tool install -U takopi
takopi --onboard
```

<!-- ### Login to Coding agents -->
<!---->
<!-- ```sh -->
<!-- codex login -->
<!-- claude login -->
<!-- ``` -->
<!---->
<!-- ### Authenticate gh and git with GitHub -->
<!---->
<!-- ```sh -->
<!-- gh auth login -->
<!-- ``` -->
<!---->
<!-- ```sh -->
<!-- devcontainer up --workspace-folder . -->
<!-- devcontainer exec --workspace-folder . fish -->

### Devcontainer

running agents unattended (yolo mode) is best done in a devcontainer. it provides isolation and lets you skip permission prompts. you will need docker, i prefer orbstack as a drop-in replacement.

I made a handy devcontainer script:

```sh
./devcontainer/install.sh self-install
devc /path/to/repo # ← you are in tmux with claude and codex
```

## Development

### [worktrunk](https://worktrunk.dev/)

a more full-featured option. it closely matches the create → pr → merge → cleanup cycle and has nice extras like auto-running install scripts or generating commits with [llm](https://llm.datasette.io/en/stable/) cli.

#### config

to match my naming structure, i put this in `~/.config/worktrunk/config.toml`:

```toml
worktree-path = ".worktrees/{{ branch }}"
```

#### use

- `wt switch -c -x codex feat/branch` — switch to a worktree and run codex
- `wt merge` — squash, rebase, merge into master, remove worktree and branch
- `wt step commit` — commit based on the diff and previous commit style
- `wt remove` — remove worktree and prune branch
- `wt select` — interactive switcher showing all worktrees and diff from master

### relative worktrees

by default, git stores absolute paths in worktree metadata. this breaks if you use devcontainer. git 2.48+ added relative path support.

enable with `git config --global worktree.useRelativePaths true`

new worktrees will use relative paths in all repos. to migrate existing worktrees to relative paths `git worktree repair`

running agents unattended (yolo mode) is best done in a devcontainer. it provides isolation and lets you skip permission prompts. you will need docker, i prefer [orbstack](https://orbstack.dev/) as a drop-in replacement.

I made a handy devcontainer script:

```sh
./devcontainer/install.sh self-install
devc /path/to/repo  # ← you are in tmux with claude and codex
```

read more [devcontainer/readme.md](devcontainer/readme.md).

### plan and review

for architecture, refactors, debugging, or "tell me what to fix next" reviews, just give the model the repo.

most people reach for repomix / code2prompt and feed the model a giant xml/md. that's outdated practice.

upload a zip made directly by git:

```sh
git archive HEAD -o code.zip
# if you need only part of the repo:
git archive HEAD:src -o src.zip
```

this works with gpt pro, claude, and gemini.

if you want context from commit messages, prior attempts, regressions, gpt and claude can also understand a git bundle:

```sh
git bundle create repo.bundle --all
```

## Special Thanks

Formed from [agents by banteg](https://github.com/banteg/agents/blob/master/readme.md)
