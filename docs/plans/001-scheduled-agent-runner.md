# 001 Scheduled Agent Runner

## Summary

This plan covers a portable, container-local scheduler tool that runs inside an existing Linux Docker container and manages scheduled coding-agent jobs. The first implementation targets `codex` only, with per-task session continuity based on the agent's unique session ID, Telegram notifications, non-interactive CLI subcommands, and human-friendly scheduling input using a constrained grammar.

## Target Branch

`feat/scheduled-agent-runner`

## Assumptions

- The runtime already has `codex` installed and authenticated.
- The tool runs inside an existing long-lived Linux container.
- Initial scope is `codex` only; `claude` remains explicitly out of scope.
- Prompts are stored inline per task.
- Telegram uses one global bot token and per-task chat IDs.
- Model defaults are centrally configured and user-overridable through a dedicated config subcommand.
- Task scheduling must expose a session option, with `fresh` as the default per run and `resume` as the explicit opt-in mode.

## Verified Research

- [001-codex-session-contract.md](../research/001-codex-session-contract.md) verifies the installed `codex` CLI behavior on `codex-cli 0.116.0`.
- `codex exec --json` emits `thread.started` with a durable `thread_id`.
- `codex exec resume --json <thread_id>` resumes the same session in non-interactive mode.
- Resume should reuse the stored model to avoid model-drift warnings.

## Locked Decisions

- Default same-task overlap behavior is `queue`.
- Same-task concurrency is out of scope for the first implementation and can be added later as an explicit extension.
- The persistent backend is SQLite plus append-only log files for run output.
- Human-friendly scheduling uses a constrained documented grammar rather than free-form natural language.
- The first release is non-interactive and scriptable.
- Default session mode is `fresh`; `resume` is an explicit per-task option.

## Recommended Direction

- Use an internal scheduler process so task/session logic stays portable inside the container.
- Persist tasks, session IDs, run history, queue state, and scheduler state in SQLite.
- Store full run output in log files referenced by the database.
- Keep the first release `codex`-only and non-interactive.
- Reject schedule inputs outside the supported grammar with explicit validation errors.

## Accepted Schedule Grammar

The first implementation should accept only the following forms:

- `every <int>m`
- `every <int>h`
- `in <int>m`
- `in <int>h`
- `daily HH:MM`
- `weekdays HH:MM`
- `<day-list> HH:MM` where `day-list` is a comma-separated subset of `mon,tue,wed,thu,fri,sat,sun`
- `cron "<5-field-expression>"`

Examples:

- `every 30m`
- `every 6h`
- `in 5m`
- `in 2h`
- `daily 09:00`
- `weekdays 14:30`
- `mon,wed,fri 18:45`
- `cron "0 9 * * 1-5"`

Anything outside this grammar is rejected with a validation error.

## Priority And Dependency Map

### Sequential

1. Ticket 1 defines the contract and records the architecture decision.
2. Ticket 2 establishes the SQLite state layer.
3. Ticket 3 establishes the config contract and default-model commands.
4. Ticket 4 adds schedule parsing and the scheduler engine.
5. Ticket 5 adds the `codex` runner and session handling.
6. Ticket 6 adds Telegram delivery and output summarization.
7. Ticket 7 adds task-management CLI integration.

### Parallel Candidates

- Ticket 6 can begin after Ticket 5 if run-record interfaces are stable.
- Test expansion can happen in parallel once each module interface is stable.

## Ticket 1: Define Spec And ADR

**Priority:** P0

**Goal**

Lock the product contract before implementation so the scheduler, persistence, queueing, and session semantics are explicit and reviewable.

**Checklist**

- Create normative specification for task model and CLI contract.
- Create user-flow doc for task lifecycle.
- Create ADR for internal scheduler and SQLite-backed persistence.
- Record the locked overlap policy and rejected alternatives.

**Tasks**

- Add `specs/spec.md` covering commands, config, task schema, queue behavior, session semantics, and notification behavior.
- Add `specs/user-flow.md` covering schedule registration, queued reruns, run execution, session reuse, and remove flows.
- Add `docs/adr/001-internal-scheduler-state-store.md` documenting why the scheduler runs inside the tool process with SQLite state.
- Record why same-task concurrency is deferred from the first release.

**Definition of Done**

- A reviewer can describe the supported CLI, task schema, and runtime behavior without reading code.
- The overlap policy, persistence backend, and accepted schedule grammar are explicitly locked.
- The ADR states trade-offs and rejected alternatives.

**Approach**

Start with written contracts because the repo currently lacks a domain spec. This keeps follow-on tickets small and prevents rework in storage, scheduler, and CLI layers.

**Files In Scope**

- `specs/spec.md`
- `specs/user-flow.md`
- `docs/adr/001-internal-scheduler-state-store.md`

**Trade-offs**

- Writing the docs first adds short-term overhead but sharply reduces API churn.
- Locking the architecture early reduces churn in state, scheduler, and CLI layers.

**Conceptual Snippet**

```text
task:
  id: "nightly-refactor"
  schedule: "weekdays 09:00"
  schedule_norm: { kind: "weekly_set", days: ["mon","tue","wed","thu","fri"], time: "09:00" }
  prompt: "Review repo and propose cleanup"
  agent: "codex"
  model: "gpt-5.4"
  overlap_policy: "queue"
  session_mode: "fresh" | "resume"
  session_id: "agent-provided-id"
  telegram_chat_id: "123456"
```

## Ticket 2: SQLite State Store

**Priority:** P0

**Goal**

Create the durable SQLite-backed state layer for tasks, session IDs, run history, queue records, and scheduler bookkeeping.

**Checklist**

- Define the SQLite schema for tasks, runs, queued executions, and scheduler metadata.
- Add schema bootstrap and migration handling for first run.
- Add repository methods for task, run, queue, and session persistence.
- Add tests for schema bootstrap and persistence behavior.

**Tasks**

- Define tables for tasks, runs, run_queue, and scheduler_state.
- Persist `task_id`, prompt, agent, model, normalized schedule, overlap policy, session mode, latest `session_id`, and Telegram chat ID.
- Persist run status, timestamps, summary, exit code, and log path.
- Add repository-level support for queued same-task runs and dequeue order.

**Definition of Done**

- State survives process restart inside the container.
- Task/session/run records can be loaded without scheduler logic.
- Queue state survives process restart.

**Approach**

Use SQLite as the single source of truth for state. That keeps query paths simple for listing tasks, resuming sessions, queueing overlaps, and recovering after restart.

**Files In Scope**

- `src/state/*`
- `tests/state_*`

**Trade-offs**

- SQLite adds a dependency but keeps task/run/session/queue joins reliable.
- Flat files remain useful for large logs, but not as the primary state store.

**Conceptual Snippet**

```text
tasks(id, prompt, agent, model, schedule_norm, overlap_policy, session_mode, session_id, chat_id)
runs(id, task_id, status, started_at, finished_at, summary, exit_code, log_path)
run_queue(id, task_id, enqueued_at, run_after)
scheduler_state(key, value)
```

## Ticket 3: Config Contract And Default Model Commands

**Priority:** P1

**Goal**

Define the `config.toml` contract and expose subcommands for inspecting and updating global defaults without mixing that work into the task lifecycle CLI.

**Checklist**

- Define `config.toml` fields and environment-backed secret references.
- Add config read/write support for global defaults.
- Add default-model inspection and update commands.
- Add tests for config validation and mutation.

**Tasks**

- Define config fields for default agent, default model, data directory, and Telegram bot token reference.
- Support `env:VAR_NAME` style secret references for sensitive values.
- Implement `config get-default-model` and `config set-default-model`.
- Validate model overrides against the configured allowlist strategy.

**Definition of Done**

- Config defaults can be read and updated predictably.
- Secret references are documented and validated.
- Default-model commands do not depend on scheduler or runner code.

**Approach**

Keep global configuration separate from runtime task state. That makes the config commands small, reviewable, and independent of scheduler internals.

**Files In Scope**

- `src/config.*`
- `config.toml.example`
- `tests/config_*`

**Trade-offs**

- Separating config and state adds one more module boundary, but reduces CLI coupling and keeps tickets smaller.
- Allowlist validation adds a little friction, but prevents silent typos in model selection.

**Conceptual Snippet**

```text
[defaults]
agent = "codex"
model = "gpt-5.4"
data_dir = "/data/scheduled-agent-runner"

[models]
allow = ["gpt-5.4", "gpt-5.4-mini"]

[telegram]
bot_token = "env:TG_BOT_TOKEN"
```

## Ticket 4: Schedule Parser And Internal Scheduler

**Priority:** P1

**Goal**

Support deterministic human-friendly schedules and portable execution inside the container.

**Checklist**

- Implement the accepted schedule grammar only.
- Convert normalized schedules into next-run timestamps.
- Implement scheduler loop, queueing behavior, and restart recovery.
- Add tests for parsing, next-run calculation, queueing, and missed-run handling.

**Tasks**

- Parse only the accepted grammar from this plan and the spec.
- Normalize user input into a canonical schedule representation stored in SQLite.
- Implement a scheduler loop that scans due tasks and dispatches jobs safely.
- Queue same-task runs instead of running them concurrently when a prior run is active.
- Handle restart recovery by recalculating due runs from persisted state.

**Definition of Done**

- Supported schedule strings round-trip through parse and serialization.
- The scheduler can compute next runs deterministically.
- Due runs for an already-active task are queued rather than dropped or run concurrently.
- Restart does not lose registered tasks or queued runs.

**Approach**

Constrain the accepted language to a small documented grammar instead of open-ended natural language. That keeps the CLI ergonomic without introducing ambiguous parsing behavior.

**Files In Scope**

- `src/schedule/*`
- `src/scheduler/*`
- `tests/schedule_*`
- `tests/scheduler_*`

**Trade-offs**

- Supporting only a constrained grammar is less magical, but much easier to validate and maintain.
- Queue-first overlap handling is safer for session continuity, but may delay repeated runs under heavy task load.

**Conceptual Snippet**

```text
parse("weekdays 09:30") -> {
  kind: "weekly_set",
  days: ["mon", "tue", "wed", "thu", "fri"],
  time: "09:30"
}
```

## Ticket 5: Codex Runner And Session Continuity

**Priority:** P1

**Goal**

Run scheduled `codex` jobs, preserve the coding-agent session ID per task when resume mode is enabled, and support fresh-per-run or explicit resume behavior.

**Checklist**

- Define the `codex` command invocation contract.
- Implement task execution with prompt injection, model selection, and session-mode handling.
- Capture and persist the agent session ID for each task.
- Add tests for runner argument building and session update behavior.

**Tasks**

- Build a runner abstraction for `codex` with explicit command arguments.
- Support per-task `session_mode` values that decide whether to start fresh by default or resume prior session when explicitly configured.
- Persist the `thread_id` emitted by the `thread.started` JSON event after a successful fresh run.
- Resume multi-turn tasks with `codex exec resume --json <session_id> -m <stored-model>`.
- Capture stdout/stderr for summarization and run records.

**Definition of Done**

- A task run records the exact session ID associated with that task when a fresh run creates one.
- Resume behavior reuses the stored session identifier only when `session_mode=resume`.
- Fresh mode does not require a prior session ID and remains the default scheduling behavior.
- Resume behavior reuses the stored model unless the user intentionally resets or replaces the session.
- Failed runs preserve diagnostics without corrupting task state.

**Approach**

Treat the agent session ID as external truth owned by the coding agent, and store it directly against each task instead of inventing a parallel session abstraction. The runner should consume the supported JSON event stream rather than scraping Codex internal files.

**Files In Scope**

- `src/agents/codex_*`
- `src/execution/*`
- `tests/agents_*`
- `tests/execution_*`

**Trade-offs**

- Depending on the agent session contract keeps behavior aligned with the actual tool, but requires careful validation of CLI output or metadata.
- A fake internal session abstraction would hide useful agent-native behavior and create drift.

**Conceptual Snippet**

```text
codex exec --json \
  --model "$MODEL" \
  "$PROMPT"

codex exec resume --json \
  "$SESSION_ID" \
  --model "$MODEL" \
  "$PROMPT"
```

## Ticket 6: Telegram Notifications And Output Summaries

**Priority:** P2

**Goal**

Send concise Telegram notifications for start, success, and failure events with output summaries tied to task runs.

**Checklist**

- Implement Telegram client and message formatting.
- Add output summarization policy.
- Connect notifications to run lifecycle events.
- Add tests for payload construction and truncation behavior.

**Tasks**

- Read bot token from config or environment-backed config reference.
- Support per-task chat ID routing.
- Send start, success, and failure messages with task name, model, status, timestamps, and output summary.
- Include log path or run ID in notifications when useful.

**Definition of Done**

- Notifications are emitted for the three required lifecycle events.
- Long output is truncated deterministically.
- Messaging failures are recorded without crashing the scheduler loop.

**Approach**

Keep the message contract narrow and operationally useful rather than sending full transcripts. The main job of Telegram is observability, not archival.

**Files In Scope**

- `src/notify/*`
- `tests/notify_*`

**Trade-offs**

- Short summaries are more reliable and less noisy, but may omit some debugging detail.
- Full transcript delivery would be expensive, noisy, and likely exceed Telegram limits.

**Conceptual Snippet**

```text
[task: nightly-refactor]
status: failed
model: gpt-5.4
session: sess_123
summary: command exited non-zero after repository analysis
log: runs/2026-04-21T01-00-00Z.log
```

## Ticket 7: Non-Interactive Task CLI

**Priority:** P2

**Goal**

Expose a stable task-management CLI for registering, checking status, pausing, resuming, editing, and removing scheduled tasks.

**Checklist**

- Add subcommands for `status`, `schedule`, and `remove`.
- Validate inputs before persisting tasks.
- Support clear machine-readable and human-readable outputs.
- Add CLI integration tests.

**Tasks**

- Implement `schedule` for task creation with prompt, model, schedule, session mode, and chat ID inputs.
- Implement `status` with task status, next run, last run, current session ID, and overlap policy.
- Implement `remove` for scheduled task deletion.
- Support machine-readable output for `status` in addition to human-readable output.

**Definition of Done**

- A user can manage the full task lifecycle for scheduled tasks without editing files manually.
- Error messages are specific enough to correct bad input quickly.
- CLI tests cover happy path and invalid input handling.

**Approach**

Keep the first task CLI non-interactive and scriptable. That fits container automation better and avoids coupling the core logic to a wizard interface.

**Files In Scope**

- `src/cli/*`
- `src/main.*`
- `tests/cli_*`

**Trade-offs**

- Non-interactive CLI is less beginner-friendly than a wizard, but better for automation and repeatability.
- Human-readable output alone is insufficient once other scripts need to integrate with the tool.

**Conceptual Snippet**

```text
runner schedule \
  --task nightly-refactor \
  --when "weekdays 09:00" \
  --prompt "Review repo and propose cleanup" \
  --model gpt-5.4 \
  --session-mode fresh \
  --chat-id 123456
```

## PR Mapping

- Ticket 1 -> PR 1 on `feat/scheduled-agent-runner`
- Ticket 2 -> PR 2 stacked on `feat/scheduled-agent-runner`
- Ticket 3 -> PR 3 stacked on `feat/scheduled-agent-runner`
- Ticket 4 -> PR 4 stacked on `feat/scheduled-agent-runner`
- Ticket 5 -> PR 5 stacked on `feat/scheduled-agent-runner`
- Ticket 6 -> PR 6 stacked on `feat/scheduled-agent-runner`
- Ticket 7 -> PR 7 stacked on `feat/scheduled-agent-runner`

Each ticket maps to one small chunk and one reviewable commit or PR.

## Review Focus

- Proposed approach: favor internal scheduler plus SQLite-backed state over cron glue so session continuity remains first-class.
- Feasibility: session ID capture and resume are now verified locally; the remaining product risk is policy around user-initiated model changes on resumed tasks.
- Ticket granularity: each ticket is scoped to a small reviewable diff with a single responsibility.
- Priority and dependencies: Tickets 1 through 5 are sequential foundations; Ticket 6 depends on run outputs; Ticket 7 is final integration.
- Risks: backward compatibility is low risk because this is greenfield, forward compatibility depends on agent CLI stability, maintainability depends on keeping schedule parsing and runner contracts narrow.

## Risks And Mitigations

- User-initiated model changes on an existing resumed task may create confusing continuity semantics.
  Mitigation: default to fresh-session reset when the model changes unless an explicit resume override is provided.
- Same-task overlap handling could grow complicated if concurrency is added later.
  Mitigation: lock the first release to queueing and represent queue state explicitly in SQLite.
- Container restarts may interrupt in-flight runs.
  Mitigation: persist run states and recover gracefully on restart.
- Telegram delivery can fail independently of agent execution.
  Mitigation: decouple notification failure from job failure and log both separately.

## Confidence Notes

- `>90%`: queue-based overlap policy, SQLite state direction, non-interactive CLI shape, per-task session persistence, Telegram routing model.
- `95%`: exact `codex` session capture via `thread.started` and resume via `codex exec resume --json <session_id>`.
- `80-85%`: product policy for model changes on an existing resumed task.
- `>90%`: constrained schedule grammar and ticket dependency order.
