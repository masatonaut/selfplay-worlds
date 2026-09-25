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

## Git and publishing: the owner does these, never the agent

- Do not run `git add`, `git commit`, `git push`, `git merge`, `git rebase`, `git reset`, create tags, or force push.
- Do not add Co-Authored-By trailers or any AI attribution.
- You may run `git status`, `git diff`, `git diff --stat` and `git log`, and propose commit groups and messages.
- Do not publish anything, and do not remove unrelated files.

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
