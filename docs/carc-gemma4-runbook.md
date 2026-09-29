# CARC Gemma 4 vLLM runbook

This is a prepared procedure, not a record of a completed GPU run. Do not execute the allocation command until the repository owner explicitly approves it.

## What was inspected

The repository CARC guide and environment script were inspected. ProjectStarter's current `vLLMModel` uses an OpenAI compatible base URL and disables hosted API rate limiting. Its usage handling preserves token metadata. No code was copied. Neither reference repository contains `install_vllm_cuda_12.sh`, and that script is not present in this local workspace. On CARC, locate it and existing environments before installing anything:

```bash
find "$HOME" /project2/jonmay_1426 -maxdepth 4 -type f -name 'install_vllm_cuda_12.sh' -print 2>/dev/null
find "$HOME" /project2/jonmay_1426 -maxdepth 4 -type f -path '*/bin/vllm' -print 2>/dev/null
find "$HOME" /project2/jonmay_1426 -maxdepth 4 -type d -iname '*vllm*' -print 2>/dev/null
```

Prefer a lab environment whose owner confirms it already serves Gemma 4. Do not modify a shared environment.

## 1. Read only resource check

Run on a CARC login node. These commands do not submit a job:

```bash
myaccount
noderes -c -g
sinfo -p gpu
squeue --me
```

## 2. Proposed allocation, approval required

The first attempt uses one 80 GB A100 because the published weights are about 62.5 GB and the experiment has only one short request at a time. Context is capped at 8192 tokens to leave memory for activations and KV cache.

```bash
salloc --account=jonmay_1426 --partition=gpu --constraint=a100-80gb --ntasks=1 --gpus-per-task=a100:1 --cpus-per-task=8 --mem=128G --time=02:00:00
```

Requested resources: one A100 80 GB GPU, 8 CPUs, 128 GB host memory, and 2 hours. Purpose: verify the existing vLLM environment, serve `google/gemma-4-31B-it`, make one smoke request, and run one three player Coup episode. If this cannot fit, stop and request new approval before asking for two GPUs.

## 3. Verify the allocated node and environment

```bash
hostname
echo "$SLURM_JOB_ID"
nvidia-smi
nvcc --version 2>/dev/null || true
module list 2>&1
```

Activate the lab's confirmed environment. The path below is deliberately a placeholder until the read only search identifies it:

```bash
source <KNOWN_GOOD_VLLM_ENV>/bin/activate
python -c 'import vllm, torch; print("vllm", vllm.__version__); print("torch", torch.__version__); print("cuda", torch.version.cuda)'
hf auth whoami
```

CARC's current Gemma 4 guide gives a vLLM 0.28 CUDA 12.9 wheel as a fallback. Installation is a separate change and should only be used if the lab has no known good environment.

## 4. Start the server

Run inside `tmux` on the allocated GPU node:

```bash
mkdir -p runs/carc-gemma4
export HF_HOME="/scratch1/$USER/huggingface"
export VLLM_USE_FLASHINFER_SAMPLER=0
vllm serve google/gemma-4-31B-it \
  --host 127.0.0.1 \
  --port 8000 \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.95 \
  > runs/carc-gemma4/vllm-server.log 2>&1 &
export VLLM_SERVER_PID=$!
```

Use the scratch cache only after confirming this location with the lab. The server listens on loopback and does not need an API key for this single node experiment.

## 5. Health check and one smoke request

```bash
until curl --fail --silent http://127.0.0.1:8000/health >/dev/null; do sleep 10; done
curl --fail --silent http://127.0.0.1:8000/v1/models
curl --fail --silent http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"google/gemma-4-31B-it","messages":[{"role":"user","content":"Reply with exactly: ready"}],"max_tokens":16,"temperature":1.0,"top_p":0.95,"top_k":64}'
```

## 6. Run one full Coup episode

```bash
export VLLM_BASE_URL=http://127.0.0.1:8000/v1
uv sync --extra llm
uv run --extra llm python examples/run_coup.py \
  --players 3 \
  --seed 0 \
  --agents llm \
  --backend vllm \
  --model google/gemma-4-31B-it \
  --temperature 1.0 \
  --top-p 0.95 \
  --top-k 64 \
  --structured-output \
  --output runs/carc-gemma4/coup-gemma4-seed0.json \
  --checkpoint runs/carc-gemma4/coup-gemma4-seed0.checkpoint.json
```

Thinking is disabled because the system prompt does not include the Gemma 4 thinking trigger. Private reasoning is not requested or stored.

## 7. Validate artifacts

```bash
uv run python -c 'import json; from pathlib import Path; p=Path("runs/carc-gemma4/coup-gemma4-seed0.json"); d=json.loads(p.read_text()); assert d["result"]; assert d["events"]; assert d["result"]["usage"]["model_calls"] > 0; print(d["result"])'
uv run python -c 'import json; from pathlib import Path; p=Path("runs/carc-gemma4/coup-gemma4-seed0.checkpoint.json"); d=json.loads(p.read_text()); assert d["schema_version"] == "1.0"; assert "game_state" in d and "agent_states" in d; print(p)'
```

## 8. Release the GPU

```bash
kill "$VLLM_SERVER_PID"
wait "$VLLM_SERVER_PID" 2>/dev/null || true
exit
```

Leaving the allocation shell releases the interactive job. From another CARC shell, use `scancel <job_id>` only if the allocation did not end normally.
