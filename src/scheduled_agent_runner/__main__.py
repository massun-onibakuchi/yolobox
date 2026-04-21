"""Where: module entrypoint. What: delegate to the CLI main function. Why: support python -m scheduled_agent_runner."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())

