# Benchmark sweep runbook

How to (re)run the zork-bench model sweep that feeds the README plots, end to
end, on a machine you can leave running. Written 2026-06-14.

This sweep adds frontier closed models (via OpenRouter) and one native-Anthropic
model to the existing six open-weight Fireworks models, then regenerates the
plots in `benchmark/results/`.

> **Do not run this on a laptop you need to close.** A full sweep is many hours
> (see [Time](#time-estimate)). Run it on a server / always-on machine under
> `tmux`, `screen`, or `nohup` so it survives disconnects and sleep.

---

## 1. What it produces

`benchmark/analyze.py` walks `benchmark/results/<nickname>/<map_mode>/` and
regenerates:

- `room_discovery.png` and `tokens_per_turn.png` (shown in the README)
- `model_comparison.png`, `score_progression.png`
- `benchmark_results.csv` (per-session metrics)

New model runs auto-appear in every plot. **No plotting code changes are needed**
when adding models, the analyzer discovers them from the directory tree.

---

## 2. Prerequisites

```bash
# 1. Clone and enter the repo
git clone https://github.com/mnky9800n/zork-bench.git
cd zork-bench

# 2. Build the game container (bocfel + remglk). Required once.
docker build -t zork-harness-game .

# 3. Install Python deps
uv sync

# 4. Create .env in the repo root (it is gitignored). The sweep script loads it
#    automatically and OVERRIDES any inherited shell keys, so the keys below are
#    the ones that get billed.
cat > .env <<'EOF'
FIREWORKS_API_KEY=fw-...
OPENROUTER_API_KEY=sk-or-...
ANTHROPIC_API_KEY=sk-ant-...
EOF
```

Which keys are needed depends on which models you run. The default roster uses
**all three** (Fireworks + OpenRouter + Anthropic). The script's pre-flight only
checks the keys for backends actually present in the roster.

> ⚠️ **Key hygiene.** The harness reads `os.environ` directly and does **not**
> auto-load `.env`. The sweep script (`run_benchmark.sh`) is what sources `.env`.
> If you run the CLI by hand, `source` the file first (see §6) or it will fall
> back to whatever key is in your shell profile, which may be the wrong account.

---

## 3. The roster

Defined in `benchmark/run_benchmark.sh` (index-aligned `NAMES` / `BACKENDS` /
`MODELS` / `THINKING` arrays). Each model runs in all three map modes
(`none`, `explore`, `full`).

| Nickname | Backend | Model ID | `--thinking` | Status |
|---|---|---|---|---|
| gpt-oss-120b | fireworks | `accounts/fireworks/models/gpt-oss-120b` | off | existing |
| minimax-m2p7 | fireworks | `accounts/fireworks/models/minimax-m2p7` | off | existing |
| glm-5p1 | fireworks | `accounts/fireworks/models/glm-5p1` | off | existing |
| kimi-k2.5 | fireworks | `accounts/fireworks/models/kimi-k2p5` | off | existing |
| deepseek-v3p2 | fireworks | `accounts/fireworks/models/deepseek-v3p2` | off | existing |
| cogito-671b | fireworks | `accounts/fireworks/models/cogito-671b-v2-p1` | off | existing |
| **gpt-5p4** | openrouter | `openai/gpt-5.4` | **on** | new |
| **gemini-3p1-pro** | openrouter | `google/gemini-3.1-pro-preview` | **on** | new |
| **deepseek-r1** | openrouter | `deepseek/deepseek-r1` | **on** | new |
| **qwen3-235b** | openrouter | `qwen/qwen3-235b-a22b-2507` | off | new |
| **claude-sonnet-4-6** | anthropic | `claude-sonnet-4-6` | off | new |

Reasoning models run with `--thinking` (sets `reasoning_effort=high` and a larger
output cap) so their reasoning tokens are not truncated at the small default cap.

### Why qwen3-235b and not qwen3-max

`qwen/qwen3-max` was the original pick but is **blocked on our OpenRouter
account**: it only routes through providers that require a data-policy opt-in,
which our account (no admin access to change) disallows. The error is:

```
No endpoints available matching your guardrail restrictions and data policy.
Configure: https://openrouter.ai/settings/privacy
```

`qwen/qwen3-235b-a22b-2507` is the open-weight replacement: unrestricted
providers, ~$0.09/M, smoke-validated. If you later gain admin access and enable
the data policy, you can switch the roster back to `qwen/qwen3-max`.

---

## 4. How the sweep script behaves

`benchmark/run_benchmark.sh` runs every `(model x map_mode)` config sequentially
and writes to `benchmark/results/<nickname>/<mode>/`.

Key behaviors:

- **Loads `.env`** at the top, overriding inherited shell keys.
- **Per-backend key check**: only requires the API key for backends in the roster.
- **Skip-already-done guard**: a config is skipped if it already has a
  `session_*.jsonl` with at least `COMPLETE_TURNS` turns (default **50**). This is
  a turn-count test, not "has a summary record", because 5-turn smoke runs and
  `api_error` stubs also write summaries. So re-running fills gaps and adds new
  models without re-paying for finished runs.
- **Retries** each failed config once after 30s (plus the harness now retries
  transient LLM API errors with backoff inside a run).

Environment overrides:

| Var | Default | Effect |
|---|---|---|
| `MAX_TURNS` | 500 | Turns per run. `MAX_TURNS=20` for a cheap smoke. |
| `COMPLETE_TURNS` | 50 | A config with a session this long is treated as done and skipped. |
| `FORCE` | (unset) | `FORCE=1` re-runs every config, even completed ones. |

### What a default run will do right now

With the current data on disk, a default run executes **19 configs** and skips
the 14 that already have real data:

- 12 new OpenRouter configs (gpt-5p4, gemini-3p1-pro, deepseek-r1, qwen3-235b × 3 modes)
- 2 Claude Sonnet 4.6 (explore, full; `none` already has a ~478-turn run)
- 5 Fireworks gap-fills (cogito ×3, deepseek-v3p2 explore/full, all prior `api_error` failures, may fail again fast)

To preview exactly what would run without spending anything (run with `bash`;
the `ls` form keeps it working under zsh too):

```bash
# Lists RUN/skip per config using the same threshold the script uses.
for n in gpt-oss-120b minimax-m2p7 glm-5p1 kimi-k2.5 deepseek-v3p2 cogito-671b \
         gpt-5p4 gemini-3p1-pro deepseek-r1 qwen3-235b claude-sonnet-4-6; do
  for m in none explore full; do
    d="benchmark/results/$n/$m"; mx=0
    for f in $(ls "$d"/session_*.jsonl 2>/dev/null); do
      t=$(grep -c '"type": *"turn"' "$f" 2>/dev/null || echo 0); (( t > mx )) && mx=$t; done
    (( mx >= 50 )) && echo "skip $n/$m ($mx)" || echo "RUN  $n/$m ($mx)"
  done
done
```

---

## 5. Smoke test first (do this once)

Validates Docker + RemGlk + each backend + tool-calling + reasoning capture
before committing to the full run. Cheap (5 turns each, a few cents total).

```bash
set -a; . ./.env; set +a   # load keys into this shell

uv run zork-harness --backend fireworks  --model accounts/fireworks/models/glm-5p1 \
  --map-mode none --max-turns 5 --session-dir sessions/smoke-fw
uv run zork-harness --backend openrouter --model openai/gpt-5.4 \
  --map-mode none --max-turns 5 --thinking --session-dir sessions/smoke-gpt54
uv run zork-harness --backend openrouter --model google/gemini-3.1-pro-preview \
  --map-mode none --max-turns 5 --thinking --session-dir sessions/smoke-gemini
uv run zork-harness --backend openrouter --model deepseek/deepseek-r1 \
  --map-mode none --max-turns 5 --thinking --session-dir sessions/smoke-r1
uv run zork-harness --backend openrouter --model qwen/qwen3-235b-a22b-2507 \
  --map-mode none --max-turns 5 --session-dir sessions/smoke-qwen
uv run zork-harness --backend anthropic  --model claude-sonnet-4-6 \
  --map-mode none --max-turns 5 --session-dir sessions/smoke-claude
```

A run is healthy if it reaches turn 5 and prints a `Session data:` path with no
`api_error`. (All of these except qwen3-max were validated on 2026-06-14.)

---

## 6. Run the full sweep

### Option A — sequential, simplest (run under tmux)

```bash
tmux new -s zorksweep            # so it survives disconnect
bash benchmark/run_benchmark.sh 2>&1 | tee benchmark/sweep_$(date +%Y%m%dT%H%M%S).log
# detach with Ctrl-b then d ; reattach later with: tmux attach -t zorksweep
```

Or with `nohup`:

```bash
nohup bash benchmark/run_benchmark.sh > benchmark/sweep.log 2>&1 &
tail -f benchmark/sweep.log
```

### Option B — parallel, ~4-5x faster (same cost)

The configs are independent (separate containers + endpoints), so they can run
concurrently. This needs `.env` loaded and the Docker image built. Run from the
repo root, under tmux. Adjust `-P` (parallelism) to taste; 5 is reasonable.

```bash
set -a; . ./.env; set +a
mkdir -p benchmark/logs

# Each line: "nickname backend model thinking". One config per (model,mode).
runs() {
cat <<'TASKS'
gpt-5p4 openrouter openai/gpt-5.4 1
gemini-3p1-pro openrouter google/gemini-3.1-pro-preview 1
deepseek-r1 openrouter deepseek/deepseek-r1 1
qwen3-235b openrouter qwen/qwen3-235b-a22b-2507 0
claude-sonnet-4-6 anthropic claude-sonnet-4-6 0
TASKS
}

runs | while read name backend model think; do
  for mode in none explore full; do
    echo "$name $backend $model $think $mode"
  done
done | xargs -P 5 -L 1 bash -c '
  name=$0; backend=$1; model=$2; think=$3; mode=$4
  d="benchmark/results/$name/$mode"
  # skip if already has >=50 turns
  mx=0; for f in $(ls "$d"/session_*.jsonl 2>/dev/null); do
    t=$(grep -c "\"type\": *\"turn\"" "$f" 2>/dev/null || echo 0); (( t > mx )) && mx=$t; done
  if (( mx >= 50 )); then echo "SKIP $name/$mode ($mx turns)"; exit 0; fi
  mkdir -p "$d"
  args=(--game zork1 --backend "$backend" --model "$model" --max-turns 500 --map-mode "$mode" --session-dir "$d")
  [ "$think" = "1" ] && args+=(--thinking)
  echo "START $name/$mode"
  uv run zork-harness "${args[@]}" > "benchmark/logs/${name}_${mode}.log" 2>&1
  echo "DONE  $name/$mode (exit $?)"
'
```

Then run the 5 Fireworks gap-fills separately (or just `bash run_benchmark.sh`
afterward, which will only pick up whatever is still missing):

```bash
bash benchmark/run_benchmark.sh   # fills remaining gaps, skips everything done
```

---

## 7. After the run: regenerate plots

```bash
uv run python benchmark/analyze.py
# Outputs land in benchmark/results/: *.png + benchmark_results.csv
```

Verify completeness (every expected config has a session with many turns):

```bash
for n in gpt-5p4 gemini-3p1-pro deepseek-r1 qwen3-235b claude-sonnet-4-6; do
  for m in none explore full; do
    f=$(ls -t benchmark/results/$n/$m/session_*.jsonl 2>/dev/null | head -1)
    [ -z "$f" ] && { echo "MISSING $n/$m"; continue; }
    t=$(grep -c '"type": *"turn"' "$f")
    echo "$n/$m: $t turns"
  done
done
```

Commit the refreshed plots + CSV (results are tracked in the repo):

```bash
git add benchmark/results/*.png benchmark/results/benchmark_results.csv \
        benchmark/results/<new-model-dirs>
git commit -m "Refresh benchmark plots with new models"
```

---

## 8. Cost estimate

Cost is **input-dominated** (~100:1 input:output): the full transcript is re-sent
every turn, so a 500-turn run accumulates ~10-40M input tokens but only ~80-450K
output. Prompt caching is **not** currently enabled and would cut input cost
substantially if added later.

Rough upper bounds for the **new** models, full 3-mode sweep (planning figure
~45M input total/model):

| Model | ~Cost (3 modes) | Notes |
|---|---|---|
| qwen3-235b | ~$5 | cheapest by far |
| deepseek-r1 | ~$45-80 | heavy reasoning output inflates the range; the cost wildcard |
| gemini-3.1-pro | ~$100 | |
| gpt-5.4 | ~$130 | |
| claude-sonnet-4-6 | ~$100 | only 2 modes needed (explore, full) |
| Fireworks gap-fills | ~$10 | cogito fails fast → near zero |

**Total ballpark: ~$300-450**, billed to the `.env` keys. Trim by dropping
deepseek-r1 to non-thinking or fewer turns, or skipping the Fireworks gap-fills.

---

## 9. Time estimate

Measured from existing completed 500-turn runs: **19 min** (kimi/none, fast) to
**160 min** (glm/explore, slow). Two drivers:

- **explore/full modes are much slower** than none (more tool calls, bigger context).
- **per-turn latency grows** as the transcript balloons; reasoning models worsen this.

| Run style | Wall-clock |
|---|---|
| Sequential (Option A) | **~20-30 hours**, dominated by deepseek-r1 + explore/full |
| Parallel `-P 5` (Option B) | **~5-7 hours** |

deepseek-r1 is the largest unknown in both time and cost (its turn-1 reasoning
was ~10K characters). Consider running it last or at reduced turns.

---

## 10. Gotchas / lessons learned

- **`.env` is not auto-loaded by the harness.** Only `run_benchmark.sh` sources
  it. Hand-run CLI commands need `set -a; . ./.env; set +a` first, or they use
  the shell-profile key (possibly the wrong account).
- **qwen3-max is blocked** by OpenRouter data policy (see §3). Using qwen3-235b.
- **Reasoning models need `--thinking`** or they truncate at the 2048-token
  default output cap. Set in the `THINKING` array.
- **The skip guard uses a turn threshold**, not "has summary", so smoke runs and
  `api_error` stubs don't masquerade as complete. Use `FORCE=1` to override.
- **Run under tmux/nohup** on an always-on machine; do not depend on a laptop.
- Reasoning text is logged under the `reasoning` field of each turn record (not
  `thinking`), if you analyze transcripts.
