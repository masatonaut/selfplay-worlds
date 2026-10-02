# CARC Gemma 4 vLLM runbook

This document records the validated launcher pattern and the current Gemma experiment. It does not contain credentials, tokens, or shared-environment paths.

## Current status

The real-model path is proven with `Qwen/Qwen2.5-7B-Instruct`. CARC job `12555139` served Qwen through vLLM on one A40 and completed a full three-player Coup episode. The checkpoint and artifact report passed.

The original target is `google/gemma-4-31B-it`. Its verified cache contains 62,546,338,248 bytes of model weights. The current validation requests two same-node A40 GPUs with tensor parallelism and is pending for priority. A pending job is not a successful Gemma result.

## Proven environment isolation

The shared vLLM installation uses Python 3.12. SelfPlayWorlds uses its own Python 3.11 environment. Letting the shared `PYTHONPATH` leak into the client process causes binary-extension import failures.

The working order is:

```bash
export PYTHONPATH="<SHARED_VLLM_SOURCE>:<SHARED_VLLM_SITE_PACKAGES>"

# Start vLLM here. The server and its child processes inherit Python 3.12 paths.
start_vllm_in_background

# The running server keeps its inherited environment.
unset PYTHONPATH

# All commands below use the project Python 3.11 environment.
project_python examples/run_coup.py ...
```

Before a GPU submission, a fresh child Python process must import `vllm` and inspect `Gemma4ForConditionalGeneration`. After `unset PYTHONPATH`, another fresh process must import `openai`, `pydantic`, `pydantic_core`, and `selfplay_worlds`, with `pydantic_core` loaded from the project Python 3.11 environment.

Do not modify the shared vLLM installation.

## Current Gemma request

```text
account:     jonmay_1426
partition:   gpu
constraint:  a40
GPU:         2 x A40 48 GB on one node
CPU:         8
host memory: 120 GB
walltime:    02:00:00
model:       google/gemma-4-31B-it
```

The model is public. A CPU job downloaded and verified its two BF16 safetensor shards in scratch before GPU submission. They total 62,546,338,248 bytes, about 58.25 GiB, with no missing or incomplete files.

## vLLM configuration

```bash
vllm serve google/gemma-4-31B-it \
  --host 127.0.0.1 \
  --port 8000 \
  --download-dir <SCRATCH_HUGGING_FACE_CACHE> \
  --dtype bfloat16 \
  --tensor-parallel-size 2 \
  --language-model-only \
  --max-model-len 4096 \
  --max-num-seqs 1 \
  --gpu-memory-utilization 0.90 \
  --enforce-eager
```

This is a text-only, sequential workload. The 4096-token context limit is enough for current Coup prompts. Limiting concurrency and using eager execution leave more memory for weights and KV cache. Tensor parallelism places approximately 29.1 GiB of BF16 weights on each GPU. The batch verifies that exactly two A40 GPUs are visible and that NCCL is available before loading the model.

Gemma sampling follows the model generation configuration:

```text
temperature = 1.0
top_p = 0.95
top_k = 64
```

Thinking is not requested. Private reasoning is not stored.

## Self-running validation stages

The batch fails at the first unsuccessful stage and preserves its logs:

1. Print Slurm, node, module, CUDA, and GPU information.
2. Verify two same-node A40 GPUs and NCCL support.
3. Verify the exact repository commit and a clean tracked checkout.
4. Export the shared Python 3.12 paths and verify vLLM.
5. Verify model access.
6. Start vLLM in the background.
7. Wait for `/health` with a bounded timeout.
8. Verify `/v1/models` serves the requested model.
9. Unset `PYTHONPATH`.
10. Run one trivial chat completion.
11. Run one real Coup decision through `VLLMBackend`.
12. Run one complete three-player Coup episode with separate agent states.
13. Validate the episode, checkpoint, usage, and model-call counts.
14. Stop vLLM through the cleanup trap.

An `EngineDeadError` logged after the intentional cleanup `SIGTERM` is not an experiment failure when the batch and artifact validation have already succeeded.

## Success criteria

- The model loads and both health and model endpoints respond.
- The smoke completion returns usage metadata.
- The single Coup decision produces an accepted typed action.
- Every non-forced episode decision goes through Gemma.
- The episode reaches a winner or the explicit turn limit.
- The result records calls, tokens, latency, retries, fallbacks, and phase coverage.
- The checkpoint contains three separate agent states.
- The validation report has `valid: true`.

If the two-GPU run fails, preserve the exact failure stage, vLLM log, and memory record for both GPUs. Do not submit another GPU job without a separate diagnosis and approval.
