# CARC setup

How to develop and run this project on USC CARC (Discovery cluster).

Every statement carries one of four labels:

| Label | Meaning |
|---|---|
| **[VERIFIED ON CARC]** | We ran it on CARC on 2026-09-28 (login node `discovery2`, CPU compute node `e23-02`). |
| **[VERIFIED]** | We ran it, but only on a Mac. |
| **[CARC DOCS]** | Written in CARC's public user guides (read on 2026-09-24 and 2026-09-28). Not tried by us. |
| **[NOT YET VERIFIED]** | Nobody has checked it yet. Unknown values are placeholders such as `<model_id>`; nothing was guessed. |

## Summary

```text
Mac ──(USC VPN)──> discovery.usc.edu      login node: ssh, git, salloc only
                        │ salloc
                        v
                   CPU compute node       uv, pytest, demo, agents, OpenRouter calls
                        (GPU node only when you run a local vLLM server)
```

## Verified on CARC (2026-09-28)

| Item | Result |
|---|---|
| Login | `discovery.usc.edu` resolves only with the USC VPN on; it points to two login nodes. We landed on `discovery2.hpc.usc.edu`. USC password login worked; no Duo prompt appeared on SSH. |
| Slurm account | `jonmay_1426` is the only account `myaccount` shows, and it is the default (QOS `normal`). |
| Compute node | `salloc --account=jonmay_1426 -p debug -c 4 --time=00:50:00` was granted at once on `e23-02` (4 CPUs, 2 GB per CPU). |
| Python | A login shell on the compute node already loads `python/3.11.9` (with `gcc/13.3.0`, `openblas`, `openmpi`, `usc/13.3.0`). |
| uv | Not preinstalled. `python3 -m pip install --user uv` on the compute node installed uv 0.12.19 into `~/.local/bin`. |
| Internet from the compute node | `pypi.org`, `github.com`, `openrouter.ai` and `huggingface.co` all answered HTTP 200. |
| GitHub | An SSH key created on CARC authenticates to GitHub (`ssh -T git@github.com` greets the account owner). The clone matched `main` on GitHub. |
| `uv sync` | Succeeded; the virtual environment uses Python 3.11.9. |
| `uv run pytest` | 122 passed, 1 skipped (the skipped test needs the optional `llm` extra). |
| `uv run --extra llm pytest` | 123 passed (the OpenAI client is tested against a local fake server; no real model is called). |
| `uv run python examples/run_coup.py` | "Carol wins after 14 turns (seed 0)". The 103-line trace is identical to the one on the Mac, and the episode JSON is valid. |
| `bash scripts/carc/check_environment.sh --tests` | Runs to the end on the compute node; every section prints. |
| Claude Code | CARC's harness is present at `/etc/claude-code` on login and compute nodes, but the `claude` command is **not installed** (not on `PATH`, no module). |
| Cost | The verification job ran 2 min 36 s on 4 CPUs and was cancelled right after. |

Still **[NOT YET VERIFIED]** on CARC: installing and logging in to Claude Code, a real OpenRouter call, any GPU or vLLM run, and the VS Code options.

Two findings from CARC's documentation shape the rest of this guide:

1. **VS Code Remote-SSH is blocked on CARC.** [CARC DOCS] "Getting Started with Discovery" (updated 2026-04-29) says the Remote-SSH extension spawns too many processes on the login nodes, does not clean them up, and can lead to an account hold. CARC recommends the SSH-FS extension instead, and CARC OnDemand offers VS Code (Code Server) on compute nodes. The old guide's Slurm proxy is Option D below; ask CARC before using it.
2. **Coding agents must run on compute nodes.** [CARC DOCS] "AI Coding Agents" (updated 2026-07-16): do not run Claude Code or Codex on login nodes. [VERIFIED ON CARC] The harness it describes is installed at `/etc/claude-code`: cluster rules (`CLAUDE.md`), `managed-settings.json` (bypass mode disabled, only CARC's hooks and permission rules allowed) and `hooks/precheck.sh`.

## 1. Connect

- [CARC DOCS] Off campus, connect to a USC VPN first. Log in to `discovery.usc.edu` with your USC NetID.
- [VERIFIED ON CARC] Without the VPN the name does not resolve. With it, both login nodes answer on port 22.
- [VERIFIED ON CARC] The server offers `publickey`, `gssapi` and `password` login. Your USC password is enough; if you leave the password prompt waiting too long, the server closes the connection and you simply connect again.
- [VERIFIED ON CARC] Both login nodes present the same ED25519 host key, `SHA256:DS3uH28N7dT0tl9BiyfQWC8U2PVCZSaHLWMqm5wLa0U`. It matches the fingerprint CARC staff posted on the CARC user forum (hpc-discourse.usc.edu, topic 1142). Compare it before you accept the key on first connection.

Suggested entry for `~/.ssh/config` on your Mac (add it yourself):

```text
Host carc
    HostName discovery.usc.edu
    User <your_usc_netid>
    ControlMaster auto
    ControlPath ~/.ssh/cm-%C
    ControlPersist 4h
```

`ssh carc` then logs you in. `ControlMaster` reuses the first authenticated connection for later `ssh`, `scp` and `git` commands for 4 hours, so you type the password once. [VERIFIED ON CARC] The same options given on the command line (`ssh -o ControlMaster=yes -o ControlPath=~/.ssh/cm-%C -o ControlPersist=4h -fN ...`) worked for the verification run.

- [CARC DOCS] Each user may run at most 64 processes, 4 CPU cores and 32 GB of memory on a login node. Every terminal connection costs 2 processes. Keep the number of open sessions small.

## 2. Get a compute node (CPU)

```bash
salloc --account=jonmay_1426 -p debug -c 4 --time=00:50:00   # debug: at most 1 hour
salloc --account=jonmay_1426 --time=4:00:00 --cpus-per-task=4 --mem=16G   # main, the default partition
```

- [VERIFIED ON CARC] `myaccount` lists `jonmay_1426` as the only and default account, so `--account` may also be left out.
- [VERIFIED ON CARC] CARC runs Slurm 26.05.1 with `LaunchParameters=use_interactive_step`, so an interactive `salloc` opens a shell **on the compute node** (the prompt changes from `discovery1`/`discovery2` to the node name, for example `e23-02`).
- [VERIFIED ON CARC] For scripted work, allocate without a shell and run steps inside the allocation:

```bash
salloc --account=jonmay_1426 -p debug -c 4 --time=00:50:00 --no-shell   # prints the job id
srun --jobid=<job_id> bash -l -c 'hostname'                             # runs on the compute node
scancel <job_id>                                                         # release it when done
```

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

- [NOT YET VERIFIED] `tmux attach` only works on the login node where tmux started, and `discovery.usc.edu` can send you to either one.

## 3. Editor: pick one

| Option | What runs where | Status |
|---|---|---|
| **A. Terminal** | Claude Code, vim or micro inside tmux on the compute node | Simplest. Recommended to start |
| **B. OnDemand Code Server** | VS Code in the browser, started as a Slurm job on a compute node | [CARC DOCS] supported by CARC, needs VPN |
| **C. SSH-FS extension** | Local VS Code edits files over SFTP; commands run in a terminal on the compute node | [CARC DOCS] CARC's recommendation |
| **D. Remote-SSH through a Slurm proxy** | Local VS Code, server on a compute node | Not confirmed as allowed by CARC, and the example needs `nc`, which the login node lacks (see below) |

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
- [VERIFIED ON CARC] `nc` is **not installed** on the login node (`discovery2`) or on the compute node we used, so `scripts/carc/slurm-vscode-proxy.sh.example` does not work there as written.
- Suggested `~/.ssh/config` entry on the Mac, if CARC approves the approach and the script is adapted:

```text
Host carc-dev
    User <your_usc_netid>
    ProxyCommand ssh carc bin/slurm-vscode-proxy.sh
    HostKeyAlias carc-compute
```

- [NOT YET VERIFIED] Whether all compute nodes share one host key (if not, `HostKeyAlias` produces host key warnings when you land on a different node).
- The sleeping job charges your account until its time limit. Stop it when you finish: `scancel --me --name=vscode-dev`.

Problems in the old guide, fixed in our example:

| Old guide | Problem | Our example |
|---|---|---|
| `EXCLUDE=="node-a,node-b"` | Bash stores the value `=node-a,node-b` (leading `=`), so `--exclude` receives a wrong node list. [VERIFIED] | `EXCLUDE="node-a,node-b"`, empty by default |
| `ssh -A discovery ...` | Forwards your SSH agent to a shared login node. The proxy does not need it. | no `-A` |
| hard-coded node names in exclude lists | Nodes change over time | no node names at all |

## 4. Project environment

- [VERIFIED ON CARC] A login shell on a compute node already has `python/3.11.9` loaded, which meets this project's `requires-python = ">=3.11"`. `module avail python` also lists 3.9.21, 3.10.16, 3.12.8 and 3.13.2 (3.13.2 is the default for a bare `module load python`).
- [VERIFIED ON CARC] uv is not preinstalled. Install it once, **on a compute node**, into your home directory (CARC's own agent rules also recommend `pip install --user` into `/home1`):

```bash
python3 -m pip install --user uv
export PATH="$HOME/.local/bin:$PATH"     # add this line to ~/.bashrc to keep it
```

Clone on the login node (plain `git` is fine there), then work on a compute node:

```bash
git clone git@github.com:masatonaut/selfplay-worlds.git ~/selfplay-worlds   # login node
cd ~/selfplay-worlds                                                          # compute node from here
uv sync
uv run pytest
uv run python examples/run_coup.py
bash scripts/carc/check_environment.sh --tests
```

- [VERIFIED ON CARC] `myquota`: `/home1` has 100 GiB and about 1.9 million files per user; `/scratch1` is large but **not backed up** and is purged when it fills; `/project2/jonmay_1426` is **shared by the whole group** and mostly used. The default uv cache in your home directory is fine for this project (about 100 MB including the `llm` extra).
- [NOT YET VERIFIED] Where model weights should be cached (`HF_HOME`) once vLLM is used. Ask the group before writing into `/project2`.

### GitHub from CARC

[VERIFIED ON CARC] Use a key created **on CARC**; never copy your Mac's private key to the cluster.

1. CARC already writes a `~/.ssh/config` (by Warewulf) with `Host *`, `IdentityFile ~/.ssh/cluster` and `StrictHostKeyChecking=no`. Do not delete it. Keep its backup if you change the file.
2. Create a separate key and put a `github.com` block **above** CARC's `Host *` block (SSH uses the first value it finds, so this also turns host key checking back on for GitHub):

```bash
ssh-keygen -t ed25519 -C "carc-<your_usc_netid>" -f ~/.ssh/id_ed25519_github_carc
```

```text
Host github.com
   IdentityFile ~/.ssh/id_ed25519_github_carc
   IdentitiesOnly yes
   StrictHostKeyChecking yes
```

3. Add the **public** key (`~/.ssh/id_ed25519_github_carc.pub`) to your GitHub account, either in GitHub's settings or with `gh ssh-key add` from a machine where `gh` is logged in (it needs the `write:public_key` permission).
4. Before the first connection, check GitHub's host key: `ssh-keyscan github.com | ssh-keygen -lf -` must show the fingerprints GitHub publishes (for example with `gh api meta --jq .ssh_key_fingerprints`). Then add those keys to `~/.ssh/known_hosts`.
5. `ssh -T git@github.com` should answer `Hi <your GitHub username>! You've successfully authenticated`.

## 5. CPU or GPU?

| Task | Node |
|---|---|
| Editing, tests, scripted demo, documentation | CPU (`debug` or `main`) |
| LLM agents through OpenRouter (the model runs at OpenRouter) | CPU. [VERIFIED ON CARC] the compute node reaches `openrouter.ai`. [NOT YET VERIFIED] a real model call |
| LLM agents through a local vLLM server | GPU |

[CARC DOCS] Cost in System Units (SUs) per minute: 1 CPU = 1, 4 GB memory = 1, one A100 or A40 GPU = 8, one V100 or P100 = 4. You are charged for what you reserve, not what you use.

[CARC DOCS] GPU requests use `--partition=gpu` plus `--gpus-per-task=<number>` or `--gpus-per-task=<gpu_type>:<number>`. Discovery's GPUs: L40S (48 GB), A100 (40 or 80 GB), A40 (48 GB), V100 (32 GB), P100 (16 GB). [NOT YET VERIFIED] the exact `<gpu_type>` strings: `noderes -c -p gpu`.

## 6. Local vLLM (later)

Nothing in this repository starts a model server. When a local model is needed ([NOT YET VERIFIED], none of this has been run):

```bash
salloc --account=jonmay_1426 --partition=gpu --gpus-per-task=1 --cpus-per-task=8 --mem=64G --time=2:00:00
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

## 8. Claude Code on CARC

- [VERIFIED ON CARC] The `claude` command is not installed on the login node or the compute node (not on `PATH`, no module).
- [VERIFIED ON CARC] CARC's harness is already in place at `/etc/claude-code` and applies automatically once Claude Code runs. [CARC DOCS] Its repository (github.com/uschpc/CARC-Harness-for-Coding-Agents) says CARC users install nothing for the harness; it does not describe installing the Claude Code program itself.
- [NOT YET VERIFIED] Installing Claude Code into your home directory and logging in. Do both from a compute node, never a login node.

## 9. Troubleshooting

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
| `myaccount: command not found` | a non-login shell, for example `ssh carc myaccount` | run it inside `bash -l -c '...'` or an interactive shell [VERIFIED ON CARC] |
| `uv: command not found` on a compute node | `~/.local/bin` is not on `PATH` | `export PATH="$HOME/.local/bin:$PATH"` [VERIFIED ON CARC] |
| `Invalid account or account/partition combination specified` | wrong account or partition [CARC DOCS] | check `myaccount` |
| Python crashes on the login node after importing NumPy | OpenBLAS starts too many threads for the process limit [CARC DOCS] | work on a compute node, or set `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1` |
| Locked out of the cluster | too many processes on a login node, often leftover editor servers [CARC DOCS] | contact carc-support@usc.edu |
| `salloc` waits a long time | the partition is busy or the request is large | ask for fewer resources, or use `debug` for short work |

## Sources

- CARC, Getting Started with Discovery: https://www.carc.usc.edu/user-guides/hpc-systems/discovery/getting-started-discovery
- CARC, Running Jobs: https://www.carc.usc.edu/user-guides/hpc-systems/using-our-hpc-systems/running-jobs
- CARC, AI Coding Agents: https://www.carc.usc.edu/user-guides/ai-computing/ai-coding-agents
- CARC, harness for coding agents: https://github.com/uschpc/CARC-Harness-for-Coding-Agents
- CARC user forum, host key fingerprint answer from CARC staff: https://hpc-discourse.usc.edu/t/1142
- CARC, Discovery Resource Overview: https://www.carc.usc.edu/user-guides/hpc-systems/discovery/resource-overview-discovery
- CARC, OnDemand Interactive Apps: https://www.carc.usc.edu/user-guides/carc-ondemand/interactive-apps
- CARC, HPC with Python: https://www.carc.usc.edu/user-guides/advanced-hpc-programming/programming-languages/python
