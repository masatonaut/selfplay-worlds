# References

## Code references (ideas only, no code reused)

`selfplay-worlds` is an independent codebase. The repositories below were **read for ideas**. No code was copied, forked, vendored or imported, and the project does not depend on any of them.

| Repository | What it is | What we looked at | Used here |
|---|---|---|---|
| [DhananjayAshok/ProjectStarter](https://github.com/DhananjayAshok/ProjectStarter) | A GitHub template for research projects: uv setup, YAML configs, LM inference utilities | Current `utils/lm_inference.py`: OpenAI-compatible hosted and local clients, explicit optional token counts, local vLLM with no artificial request rate, and hosted timeout/backoff logic | The same small transport boundary and explicit usage metadata. We intentionally did not copy its asynchronous batching, broad provider hierarchy, rate limiter, or hosted retry system because this project currently runs one synchronous decision at a time and local server failures should be visible |
| [DhananjayAshok/GameBoyWorlds](https://github.com/DhananjayAshok/GameBoyWorlds) | Environments for agents playing Game Boy games | Current interface and emulation registries, game-specific action and environment folders, observation rendering, and test/train environment variants | The same broad idea that games own their action and observation details behind a common environment boundary. We did not copy its registry layers or Gym/emulator state model because social games have explicit multi-agent interactions |
| [PrimeIntellect-ai/prime-rl](https://github.com/PrimeIntellect-ai/prime-rl) | A framework for reinforcement learning of language models | Nothing yet | Future reference for Milestone 5 |

**Code reused: none.** If reusing code ever becomes worthwhile (for example ProjectStarter's inference utilities), the plan is: explain why, check the license and attribution requirements, and ask before copying anything.

## Game rules

- Coup, 64 Oz. Games accessibility transcription of the rulebook: https://www.64ouncegames.com/pages/coup
- Coup, UltraBoardGames transcription of the rulebook: https://www.ultraboardgames.com/coup/game-rules.php

## Infrastructure

- USC CARC user guides (read 2026-09-24): see the source list at the end of `docs/carc-setup.md`.
- OpenRouter API base URL: `https://openrouter.ai/api/v1` (OpenAI-compatible).
- vLLM's OpenAI-compatible server (default local address used here: `http://localhost:8000/v1`).
- Gemma 4 model card and generation config: https://huggingface.co/google/gemma-4-31B-it and https://huggingface.co/google/gemma-4-31B-it/blob/main/generation_config.json. Checked 2026-09-28. The recommended baseline is `temperature=1.0`, `top_p=0.95`, `top_k=64`, with thinking disabled by omitting the thinking trigger.
- vLLM OpenAI-compatible structured outputs: https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/. Checked 2026-09-28. JSON schema response format is optional in this project.
- CARC GPU programming guide: https://www.carc.usc.edu/user-guides/advanced-hpc-programming/gpu-programming.html. It documents `a100-80gb` as the Slurm constraint for an 80 GB A100.

## Related research

The literature survey on social and strategic games as LLM environments (which games have prior benchmarks, and how close each one is) lives in the separate game scouting report, not in this repository.

- Nonomura, R. and Mori, H. (2025), [Who speaks next? Multi-party AI discussion leveraging the systematics of turn-taking in Murder Mystery games](https://doi.org/10.3389/frai.2025.1582287). The paper motivates treating next-speaker selection as an experimental policy. This repository implements only a replaceable deterministic scheduler and does not implement the paper's learned or reasoning-based selection mechanisms.

**Design note:** speaker scheduling is an experimental variable. The environment decides who is eligible; the scheduler decides the order in which eligible agents are queried.

## Architecture references

- [OpenSpiel State API](https://github.com/google-deepmind/open_spiel/blob/master/docs/api_reference/state_apply_action.md): inspired the separation between static game description, mutable state, legal actions, and transitions. Unlike OpenSpiel's low-level API, `CoupEnv.step` deliberately rechecks legality.
- [PettingZoo AEC and Parallel APIs](https://pettingzoo.farama.org/main/): inspired explicit agent cycles, changing eligible order, and collecting simultaneous actions before applying them. This project does not depend on PettingZoo and is not a PettingZoo rewrite.
- Event sourcing and snapshots: inspired append-only decision records plus periodic state snapshots. This project has neither CQRS infrastructure nor an event-replay state model.
- Actor model: inspired one independently serializable state per agent. There is no actor runtime or message bus.
- [Social Gym and SPaRTan](https://arxiv.org/abs/2608.09128): supports preferring rule-decided outcomes that can be checked without an LLM judge. This project does not claim compatibility with Social Gym.
