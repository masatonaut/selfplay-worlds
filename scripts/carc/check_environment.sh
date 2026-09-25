#!/usr/bin/env bash
# Print what this CARC session looks like. Read-only.
#
# It submits no jobs, requests no GPU, changes no files and prints no secret
# values (only whether a variable is set). Run it on the login node once and on
# a compute node once, and paste the output into docs/carc-setup.md
# ("First login checklist").
#
# Usage:
#   bash scripts/carc/check_environment.sh           # environment only
#   bash scripts/carc/check_environment.sh --tests   # also run the test suite

set -u

section() { printf '\n== %s ==\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

section "Where am I"
echo "host: $(hostname)"
echo "user: $(whoami)"
echo "date: $(date)"
case "$(hostname -s)" in
  discovery*|endeavour*)
    echo "NOTE: this looks like a LOGIN node. Tests, agents and editors belong on a compute node (salloc)." ;;
esac

section "Slurm allocation (all <none> on a login node)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-<none>}"
echo "SLURM_JOB_NODELIST=${SLURM_JOB_NODELIST:-<none>}"
echo "SLURM_JOB_PARTITION=${SLURM_JOB_PARTITION:-<none>}"
echo "SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK:-<none>}"
if have squeue; then squeue --me; else echo "squeue: not found"; fi

section "Accounts and storage (CARC commands)"
for cmd in myaccount myquota; do
  if have "$cmd"; then "$cmd"; else echo "$cmd: not found"; fi
done

section "Modules"
if type module >/dev/null 2>&1; then
  module list 2>&1
else
  echo "the 'module' command is not defined in this shell (try: bash -l scripts/carc/check_environment.sh)"
fi

section "Python and uv"
for cmd in python3 uv git nc; do
  if have "$cmd"; then echo "$cmd: $(command -v "$cmd")"; else echo "$cmd: not found"; fi
done
have python3 && python3 --version
have uv && uv --version

section "GPU"
if have nvidia-smi; then
  nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
else
  echo "no nvidia-smi (normal on CPU nodes and login nodes)"
fi

section "Network (HTTP status only, no credentials are sent)"
if have curl; then
  for url in https://openrouter.ai/api/v1/models https://pypi.org/simple/ https://huggingface.co; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 "$url" 2>/dev/null || echo "unreachable")
    echo "$url -> $code"
  done
else
  echo "curl: not found"
fi

section "Environment variables (set or not; values are never printed)"
for var in OPENROUTER_API_KEY VLLM_BASE_URL VLLM_API_KEY HF_HOME UV_CACHE_DIR; do
  if [ -n "${!var:-}" ]; then echo "$var is set"; else echo "$var is not set"; fi
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
section "Project ($repo_root)"
if have git && [ -d "$repo_root/.git" ]; then
  git -C "$repo_root" status --short --branch | head -n 5
fi
if [ "${1:-}" = "--tests" ]; then
  if have uv; then
    (cd "$repo_root" && uv run pytest -q)
  else
    echo "uv not found; see docs/carc-setup.md, section 'Project environment'"
  fi
fi
