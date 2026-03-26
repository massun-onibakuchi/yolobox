# Yolobox

> [!NOTE]
> This repository is a template for running AI coding agents in YOLO mode inside a devcontainer

## Prerequisites

## Setup

### Install Coding agent <> Telegram bridge

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
```

```sh
uv tool install -U takopi
takopi --onboard
```

### Login to Coding agents

```sh
codex login
claude login
```

### Authenticate gh and git with GitHub

```sh
gh auth login
```

```sh
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . fish
```

## Development

## Spec
