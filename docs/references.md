# References

## Code references (ideas only, no code reused)

`selfplay-worlds` is an independent codebase. The repositories below were **read for ideas**. No code was copied, forked, vendored or imported, and the project does not depend on any of them.

| Repository | What it is | What we looked at | Used here |
|---|---|---|---|
| [DhananjayAshok/ProjectStarter](https://github.com/DhananjayAshok/ProjectStarter) | A GitHub template for research projects: uv setup, YAML configs, LM inference utilities | `utils/lm_inference.py`: OpenRouter via `OPENROUTER_API_KEY`, vLLM via a base URL, one call that takes chat messages and returns text plus token counts. Conventions such as keyword-only arguments and never committing private settings | The same general shape for our own small inference layer (OpenAI-compatible client, key from an environment variable, token counts in the result). Keyword-only arguments throughout |
| [DhananjayAshok/GameBoyWorlds](https://github.com/DhananjayAshok/GameBoyWorlds) | Environments for LLM agents playing Game Boy games | A registry that returns an environment by game name, one folder per game, text rendering of observations for models, a dummy environment for tests | The same ideas: `get_game(name)`, `games/<name>/`, `render_observation`, a test fixture environment. Not its single-agent step loop, which cannot express response windows |
| [PrimeIntellect-ai/prime-rl](https://github.com/PrimeIntellect-ai/prime-rl) | A framework for reinforcement learning of language models | Nothing yet | Future reference for Milestone 5 |

**Code reused: none.** If reusing code ever becomes worthwhile (for example ProjectStarter's inference utilities), the plan is: explain why, check the license and attribution requirements, and ask before copying anything.

## Game rules

- Coup, 64 Oz. Games accessibility transcription of the rulebook: https://www.64ouncegames.com/pages/coup
- Coup, UltraBoardGames transcription of the rulebook: https://www.ultraboardgames.com/coup/game-rules.php

## Infrastructure

- USC CARC user guides (read 2026-09-24): see the source list at the end of `docs/carc-setup.md`.
- OpenRouter API base URL: `https://openrouter.ai/api/v1` (OpenAI-compatible).
- vLLM's OpenAI-compatible server (default local address used here: `http://localhost:8000/v1`).

## Related research

The literature survey on social and strategic games as LLM environments (which games have prior benchmarks, and how close each one is) lives in the separate game scouting report, not in this repository.
