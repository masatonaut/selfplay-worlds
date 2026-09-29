# CLAUDE.md

Instructions for coding agents working in this repository.

## What this is

Common environments and infrastructure for multi-agent LLM self-play in strategic social games. One real game (Coup) works end-to-end; the framework is not specific to it. Read `README.md`, then `docs/architecture.md`. Project state is in `docs/progress.md`.

## Commands

```bash
uv sync                               # install (add --extra llm for real model backends)
uv run pytest                         # all tests; no network, API key or GPU needed
uv run python examples/run_coup.py    # deterministic demo (seed 0)
```

## Git and publishing

- Normal commits and pushes to `main` are allowed after tests, diff review, and secret checks.
- Before every push, verify the effective Git identity is `Masato Ito <66577866+masatonaut@users.noreply.github.com>`, the GitHub account is `masatonaut`, and the remote is `masatonaut/selfplay-worlds`.
- Never force push, rewrite published history, or use destructive reset operations.
- Never change GitHub authentication, SSH keys, credentials, or account permissions.
- Do not add Co-Authored-By trailers or any AI attribution.
- Do not remove unrelated files.

## Secrets

- API keys come only from environment variables (`OPENROUTER_API_KEY`, `VLLM_API_KEY`). Never write a key into code, YAML, JSON, logs or docs.

## Architecture rules

- The environment is the source of truth. It never calls a model and never decides who is asked first.
- The Runner contains no game rules. It schedules by `Interaction.mode` only.
- Agents receive `observe(player)`, never `full_state()`. Any new observation needs a test that it hides what it should.
- Keep `message` and `action` separate in `AgentOutput`.
- `mode` is generic (`SINGLE`, `RESPONSE_WINDOW`, `DISCUSSION`, `SIMULTANEOUS`); `phase` is game-specific.
- Code in `tests/fixtures/` is test-only. Never describe it as an implemented game.
- Do not invent game rules. Verify them against a published rulebook and record sources and interpretations, as in `docs/coup-rules.md`.

## Style

- Small, readable code: prefer a few clear classes over frameworks, registries of registries or event buses.
- Keyword-only arguments for public functions (`def f(*, a, b)`).
- Every rule change comes with a test; `uv run pytest` must pass before you report a task as done.
- Update `docs/progress.md` when a milestone moves.
- In documentation, do not use dashes as sentence separators.

## Shell

- Prefer absolute paths or a small temporary script over long compound shell commands.

## On CARC

- Run agents, tests and editors on a compute node, never on a login node. CARC preinstalls its own agent harness; follow its prompts. See `docs/carc-setup.md`.
- Never request a GPU for tests or OpenRouter runs. GPUs are only for a local vLLM server, and this code never starts one.
