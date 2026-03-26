---
name: claude
description: Run Claude Code CLI in interactive or headless mode for coding, editing, review, discussing or any task delegation
---

# Claude Code CLI

Use this skill to run Claude Code CLI in **interactive** or **headless** mode.
Last verified against `claude --help` on 2026-02-20.

## Workflow

1. Think which mode to use: interactive or headless.
2. Assemble the command with appropriate options based on the following reference.
3. Run the CLI with pooling or minimum 500 seconds timeout.
4. Report output, exit code, and any next steps.

## When to use each mode

- Use **interactive** mode when you need multi-turn clarification, exploration, or iterative commands.
- Use **headless** mode for single-shot prompts, automation, or CI scripts.
- Prefer **interactive** if you must inspect outputs before proceeding or choose between options.
- Prefer **headless** if you already have a precise prompt and just need the result.
- Avoid mixing modes in one run unless the user asks for a follow-up.

## Quick Reference

| Use case                   | Command                                       | Notes                                                                                         |
| -------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Interactive session        | `claude`                                      | Starts an interactive session by default.                                                     |
| Headless / non-interactive | `claude -p "Your prompt"`                     | `-p/--print` prints and exits. Use for scripts/CI.                                            |
| Headles multi-turn      | `claude -p "Your prompt" -c`                   | Continues the most recent conversation for multi-turn session |
| Choose model               | `claude --model sonnet -p "Your prompt"`      | For single-shot jobs, keep `-p` so output is non-interactive.                                |
| Resume session             | `claude --resume <session-id>` or `claude -r` | `--resume <id>` resumes directly. `-r` with no ID opens the resume picker.                   |
| Permission mode            | `claude --permission-mode plan`               | Current choices: `acceptEdits`, `bypassPermissions`, `default`, `delegate`, `dontAsk`, `plan`. Recheck via `claude --help`. |
| Help                       | `claude --help`                               | Source of truth for current flags/options.                                                    |
