# CARC setup

How to develop and run this project on USC CARC (Discovery cluster).

Every statement carries one of three labels:

| Label | Meaning |
|---|---|
| **[VERIFIED]** | We ran it. So far only on a Mac, **not on CARC**. |
| **[CARC DOCS]** | Written in CARC's public user guides (read on 2026-09-24). Not yet tried by us. |
| **[TO VERIFY ON CARC]** | Needs your login to check. Unknown values are placeholders such as `<project_id>`; nothing was guessed. |

## Summary

```text
Mac ──(USC VPN)──> discovery.usc.edu      login node: ssh, git, salloc only
                        │ salloc
                        v
                   CPU compute node       tmux, Claude Code, uv, pytest, demo, OpenRouter calls
                        (GPU node only when you run a local vLLM server)
```

Two findings change the old setup guide:

1. **VS Code Remote-SSH is blocked on CARC.** [CARC DOCS] "Getting Started with Discovery" (updated 2026-04-29) says the Remote-SSH extension spawns too many processes on the login nodes, does not clean them up, and can lead to an account hold. CARC recommends the SSH-FS extension instead, and CARC OnDemand offers VS Code (Code Server) on compute nodes. The old guide's Slurm proxy puts the VS Code server on a compute node, which may avoid the problem, but CARC has not said it is allowed. Treat it as Option D below and ask first.
2. **Coding agents must run on compute nodes.** [CARC DOCS] "AI Coding Agents" (updated 2026-07-16): do not run Claude Code or Codex on login nodes. CARC preinstalls a harness under `/etc` on login and compute nodes: cluster rules the agent reads as `CLAUDE.md`, managed permission settings (bypass mode is off), and a hook that checks every shell and file action. `sbatch` and `git push` ask for confirmation.

## 1. Connect

- [CARC DOCS] On campus use the USC secure network; off campus connect to a USC VPN first (Duo 2FA). Log in to `discovery.usc.edu` with your USC NetID.
- [VERIFIED] On 2026-09-24 `discovery.usc.edu` did not resolve from this Mac (no VPN running). Only the name lookup was tried.
- [VERIFIED] `~/.ssh/config` on this Mac has no CARC entry. Nothing was changed.

Suggested entry for `~/.ssh/config` (add it yourself):

```text
Host carc
    HostName discovery.usc.edu
    User <your_usc_netid>
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 4h
```

`ssh carc` then logs you in. `ControlMaster` reuses the first authenticated connection for later `ssh`, `scp` and `git` commands for 4 hours, so you log in once.

- [TO VERIFY ON CARC] Whether SSH login itself asks for Duo (the docs only mention Duo for the VPN).
- [CARC DOCS] Each user may run at most 64 processes, 4 CPU cores and 32 GB of memory on a login node. Every terminal connection costs 2 processes. Keep the number of open sessions small.

## 2. Get a compute node (CPU)

[CARC DOCS] Two ways to start an interactive allocation:

```bash
salloc -p debug -c 4        # 4 cores for 1 hour; debug jobs are limited to 1 hour
salloc --time=4:00:00 --cpus-per-task=4 --mem=16G --account=<project_id>   # main, the default partition
```

- Project accounts look like `<PI_username>_<id>`. `myaccount` lists yours.
- [TO VERIFY ON CARC] Which account this project should charge (ask Dhananjay).

Work inside tmux so a dropped connection does not end your session (CARC has a tmux guide):

```bash
tmux new -s dev             # on the login node
salloc -p debug -c 4        # inside tmux; the shell moves to the compute node
tmux attach -t dev          # later, after reconnecting to the same login node
```

Check where you are:

```bash
hostname                    # discovery1 or discovery2 = login node; anything else = compute node
echo "$SLURM_JOB_ID"        # empty on the login node
squeue --me                 # your jobs and the nodes they run on
```

- [TO VERIFY ON CARC] `ssh carc` may land on either login node; `tmux attach` only works on the one where tmux started.

## 3. Editor: pick one

| Option | What runs where | Status |
|---|---|---|
| **A. Terminal** | Claude Code, vim or micro inside tmux on the compute node | Simplest. Recommended to start |
| **B. OnDemand Code Server** | VS Code in the browser, started as a Slurm job on a compute node | [CARC DOCS] supported by CARC, needs VPN |
| **C. SSH-FS extension** | Local VS Code edits files over SFTP; commands run in a terminal on the compute node | [CARC DOCS] CARC's recommendation |
| **D. Remote-SSH through a Slurm proxy** | Local VS Code, server on a compute node | [TO VERIFY ON CARC] not confirmed as allowed; ask carc-support@usc.edu first |

### Option D in detail (the old guide's approach)

```text
VS Code on Mac ──ssh carc-dev──> ProxyCommand: ssh carc bin/slurm-vscode-proxy.sh
                                   (runs on the login node)
                                   1. reuse or submit a sleeping job named vscode-dev
                                   2. wait until Slurm starts it on a node
                                   3. nc <node> 22
               <── the SSH session ends on the compute node; the VS Code server runs there
```

- [CARC DOCS] You may `ssh <nodename>` from a login node while your job runs on that node. The proxy relies on this.
- Script: `scripts/carc/slurm-vscode-proxy.sh.example`. Copy it to `~/bin/slurm-vscode-proxy.sh` on CARC, `chmod 700`, and fill in `ACCOUNT`.
- Suggested `~/.ssh/config` entry on the Mac:

```text
Host carc-dev
    User <your_usc_netid>
    ProxyCommand ssh carc bin/slurm-vscode-proxy.sh
    HostKeyAlias carc-compute
```

- [TO VERIFY ON CARC] Whether `nc` exists on the login nodes, and whether all compute nodes share one host key (if not, `HostKeyAlias` produces host key warnings when you land on a different node).
- The sleeping job charges your account until its time limit. Stop it when you finish: `scancel --me --name=vscode-dev`.

Problems in the old guide, fixed in our example:

| Old guide | Problem | Our example |
|---|---|---|
| `EXCLUDE=="node-a,node-b"` | Bash stores the value `=node-a,node-b` (leading `=`), so `--exclude` receives a wrong node list. [VERIFIED] | `EXCLUDE="node-a,node-b"`, empty by default |
| `ssh -A discovery ...` | Forwards your SSH agent to a shared login node. The proxy does not need it. | no `-A` |
| hard-coded node names in exclude lists | Nodes change over time | no node names at all |

## 4. Project environment

- [CARC DOCS] Python comes from modules, for example `module load gcc/13.3.0 python/3.11.9`. This project needs Python 3.11 or newer.
- [TO VERIFY ON CARC] CARC's docs do not mention uv. One way to install it without piping a script into a shell:

```bash
module load gcc/13.3.0 python/3.11.9
python3 -m pip install --user uv
export PATH="$HOME/.local/bin:$PATH"
```

On a compute node:

```bash
git clone <repository_url> selfplay-worlds
cd selfplay-worlds
uv sync
uv run pytest
uv run python examples/run_coup.py
bash scripts/carc/check_environment.sh --tests
```

- [CARC DOCS] Storage: `/home1`, `/project2`, `/scratch1`; `myquota` shows your directories and limits.
- [TO VERIFY ON CARC] Whether the uv cache and model weights should go to `/project2` or `/scratch1` instead of home (set `UV_CACHE_DIR` and `HF_HOME`).
- [TO VERIFY ON CARC] How you authenticate to GitHub from CARC (HTTPS with a token, or an SSH key created on CARC). Never copy your Mac's private key to the cluster.

## 5. CPU or GPU?

| Task | Node |
|---|---|
| Editing, tests, scripted demo, documentation | CPU (`debug` or `main`) |
| LLM agents through OpenRouter (the model runs at OpenRouter) | CPU. [TO VERIFY ON CARC] compute nodes can reach `openrouter.ai`; `check_environment.sh` prints this |
| LLM agents through a local vLLM server | GPU |

[CARC DOCS] Cost in System Units (SUs) per minute: 1 CPU = 1, 4 GB memory = 1, one A100 or A40 GPU = 8, one V100 or P100 = 4. You are charged for what you reserve, not what you use.

[CARC DOCS] GPU requests use `--partition=gpu` plus `--gpus-per-task=<number>` or `--gpus-per-task=<gpu_type>:<number>`. Discovery's GPUs: L40S (48 GB), A100 (40 or 80 GB), A40 (48 GB), V100 (32 GB), P100 (16 GB). [TO VERIFY ON CARC] the exact `<gpu_type>` strings: `noderes -c -p gpu`.

## 6. Local vLLM (later)

Nothing in this repository starts a model server. When a local model is needed ([TO VERIFY ON CARC], none of this has been run):

```bash
salloc --partition=gpu --gpus-per-task=1 --cpus-per-task=8 --mem=64G --time=2:00:00 --account=<project_id>
uv venv ~/venvs/vllm && source ~/venvs/vllm/bin/activate    # keep vLLM out of the project environment
uv pip install vllm
vllm serve <model_id> --port 8000
```

Then, in a second terminal on the same node:

```bash
export VLLM_BASE_URL=http://localhost:8000/v1
uv run --extra llm python examples/run_coup.py --agents llm --backend vllm --model <model_id>
```

Open questions: which CUDA and driver versions the GPU nodes provide, which vLLM build matches them, and where model weights should be cached.

## 7. OpenRouter key

- Never put the key in this repository, in YAML or JSON configs, or in the episode logs. The code only reads `OPENROUTER_API_KEY` from the environment.
- For one session, without leaving the key in your shell history:

```bash
read -rs OPENROUTER_API_KEY && export OPENROUTER_API_KEY    # paste, press Enter; nothing is shown
```

- To keep it: create `~/.config/selfplay-worlds/env` with an editor (one line: `export OPENROUTER_API_KEY=...`), run `chmod 600` on it, and `source` it when you need it.
- [CARC DOCS] Text sent to a model provider leaves CARC. Our prompts contain only game state.

## 8. Troubleshooting

```bash
hostname; echo "$SLURM_JOB_ID"       # where am I?
squeue --me                          # my jobs and nodes
scancel <jobid>                      # stop one job
myaccount; myquota                   # accounts, storage
jobinfo <jobid>                      # efficiency of a finished job
sinfo -p debug                       # partition state
noderes -c -p gpu                    # GPU nodes and their resources
module list; module avail python     # loaded and available modules
ps -u "$USER" | wc -l                # my processes (login node limit: 64)
```

| Symptom | Likely cause | Fix |
|---|---|---|
| `Invalid account or account/partition combination specified` | wrong account or partition [CARC DOCS] | check `myaccount` |
| Python crashes on the login node after importing NumPy | OpenBLAS starts too many threads for the process limit [CARC DOCS] | work on a compute node, or set `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1` |
| Locked out of the cluster | too many processes on a login node, often leftover editor servers [CARC DOCS] | contact carc-support@usc.edu |
| `salloc` waits a long time | the partition is busy or the request is large | ask for fewer resources, or use `debug` for short work |

## 9. First login checklist

Fill this in on your first CARC session and paste the output of `bash scripts/carc/check_environment.sh` next to it.

- [ ] VPN connected and `ssh carc` works. Duo asked on SSH: yes / no
- [ ] `myaccount`: project account to use: ______ (confirm with Dhananjay)
- [ ] `myquota`: home quota ______, project directory ______
- [ ] `salloc -p debug -c 4` works; node name looks like ______
- [ ] `module avail python`: version used ______
- [ ] uv installed; `uv run pytest` passes on the compute node
- [ ] Compute node reaches `openrouter.ai` (network section of the check script)
- [ ] Editor chosen: A / B / C (D only after CARC confirms)
- [ ] Only when vLLM is needed: `noderes -c -p gpu` for GPU type names

## Sources

- CARC, Getting Started with Discovery: https://www.carc.usc.edu/user-guides/hpc-systems/discovery/getting-started-discovery
- CARC, Running Jobs: https://www.carc.usc.edu/user-guides/hpc-systems/using-our-hpc-systems/running-jobs
- CARC, AI Coding Agents: https://www.carc.usc.edu/user-guides/ai-computing/ai-coding-agents
- CARC, Discovery Resource Overview: https://www.carc.usc.edu/user-guides/hpc-systems/discovery/resource-overview-discovery
- CARC, OnDemand Interactive Apps: https://www.carc.usc.edu/user-guides/carc-ondemand/interactive-apps
- CARC, HPC with Python: https://www.carc.usc.edu/user-guides/advanced-hpc-programming/programming-languages/python
