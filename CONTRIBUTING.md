# Contributing

Thanks for helping improve Ouroboros Workspace Bridge, part of Ouroboros by KwakWooJae.

## Setup

Use a repository checkout for v0.1 development:

```bash
uv sync
```

## Verification

Run the normal checks before opening a pull request:

```bash
for script in scripts/*.sh; do bash -n "$script"; done
bash -n install.sh
uv run python -m unittest discover -s tests
uv run python scripts/smoke_check.py
git diff --check
```

## Coding Rules

- Keep local mutation behind approval bundles.
- Do not add direct unsafe file or shell operations.
- Do not commit secrets.
- Preserve `WORKSPACE_ROOT` safety behavior.
- Keep docs and tests updated with behavior changes.
- Keep changes small and reviewable.

## Commit Style

Use short imperative commit messages, for example:

```text
Add supervisor process status
Fix action bundle rollback
Update quickstart docs
```

## Contribution License

By contributing to this repository, you agree that your contributions are licensed under the KwakWooJae Non-Commercial License 1.0.
