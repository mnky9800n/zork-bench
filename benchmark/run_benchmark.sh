#!/usr/bin/env bash
# benchmark/run_benchmark.sh
#
# Runs every (model x map mode) configuration of zork-harness sequentially.
# Results land in benchmark/results/<nickname>/<mode>/.
#
# By default a configuration is SKIPPED if it already has a completed session
# (a session_*.jsonl containing a "summary" record), so re-running only fills
# gaps and adds new models without re-paying for finished runs.
#
# Override turn count for quick tests:
#   MAX_TURNS=5 bash benchmark/run_benchmark.sh
# Force re-running already-completed configurations:
#   FORCE=1 bash benchmark/run_benchmark.sh
# Models route through Fireworks, OpenRouter, or Anthropic depending on the
# per-model backend below; the matching API key must be set for any backend used.

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve project root from script location and cd there
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Load API keys from .env if present, overriding any inherited shell values so
# runs bill the keys the project owner intends (not a stray key from a profile).
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
    echo "  [ok] loaded API keys from .env"
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_TURNS=500

MAP_MODES=("none" "explore" "full")

# Parallel arrays: index N describes one model configuration.
# Order is roughly small-to-large by parameter count so the cheap runs
# finish first and produce useful intermediate signal even if we abort.
NAMES=(
    "gpt-oss-120b"
    "minimax-m2p7"
    "glm-5p1"
    "kimi-k2.5"
    "deepseek-v3p2"
    "cogito-671b"
    "gpt-5p4"
    "gemini-3p1-pro"
    "deepseek-r1"
    "qwen3-235b"
    "claude-sonnet-4-6"
)
BACKENDS=(
    "fireworks"
    "fireworks"
    "fireworks"
    "fireworks"
    "fireworks"
    "fireworks"
    "openrouter"
    "openrouter"
    "openrouter"
    "openrouter"
    "anthropic"
)
# Empty string means omit --model flag (uses backend default).
MODELS=(
    "accounts/fireworks/models/gpt-oss-120b"
    "accounts/fireworks/models/minimax-m2p7"
    "accounts/fireworks/models/glm-5p1"
    "accounts/fireworks/models/kimi-k2p5"
    "accounts/fireworks/models/deepseek-v3p2"
    "accounts/fireworks/models/cogito-671b-v2-p1"
    "openai/gpt-5.4"
    "google/gemini-3.1-pro-preview"
    "deepseek/deepseek-r1"
    "qwen/qwen3-235b-a22b-2507"
    "claude-sonnet-4-6"
)
# "1" passes --thinking (reasoning_effort=high + larger output cap). Reasoning
# models need this or their reasoning tokens get truncated at the small default
# output cap. Index-aligned with NAMES.
THINKING=(
    "0"
    "0"
    "0"
    "0"
    "0"
    "0"
    "1"
    "1"
    "1"
    "0"
    "0"
)

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo "=== Pre-flight checks ==="

if ! docker image inspect zork-harness-game > /dev/null 2>&1; then
    echo "ERROR: Docker image 'zork-harness-game' not found." >&2
    echo "       Run: docker build -t zork-harness-game ." >&2
    exit 1
fi
echo "  [ok] Docker image zork-harness-game exists"

# Only require the API key for backends actually present in this run.
declare -A KEY_FOR_BACKEND=(
    ["fireworks"]="FIREWORKS_API_KEY"
    ["openrouter"]="OPENROUTER_API_KEY"
    ["anthropic"]="ANTHROPIC_API_KEY"
    ["openai"]="OPENAI_API_KEY"
)
USED_BACKENDS=$(printf '%s\n' "${BACKENDS[@]}" | sort -u)
for be in $USED_BACKENDS; do
    key_var="${KEY_FOR_BACKEND[$be]:-}"
    if [[ -z "$key_var" ]]; then
        echo "ERROR: no API-key mapping for backend '$be'." >&2
        exit 1
    fi
    if [[ -z "${!key_var:-}" ]]; then
        echo "ERROR: ${key_var} is not set (required for backend '$be')." >&2
        exit 1
    fi
    echo "  [ok] ${key_var} is set (backend: ${be})"
done

if ! uv run zork-harness --help > /dev/null 2>&1; then
    echo "ERROR: 'uv run zork-harness --help' failed. Is the project installed?" >&2
    exit 1
fi
echo "  [ok] zork-harness CLI is available"
echo ""

# ---------------------------------------------------------------------------
# Benchmark loop
# ---------------------------------------------------------------------------
TOTAL_RUNS=$(( ${#NAMES[@]} * ${#MAP_MODES[@]} ))
RUN_COUNT=0
START_TIME=$(date +%s)
FAILED_RUNS=()

echo "=== Starting benchmark: ${TOTAL_RUNS} runs, MAX_TURNS=${MAX_TURNS} ==="
echo ""

for model_idx in "${!NAMES[@]}"; do
    nickname="${NAMES[$model_idx]}"
    backend="${BACKENDS[$model_idx]}"
    model="${MODELS[$model_idx]}"
    thinking="${THINKING[$model_idx]}"

    for mode in "${MAP_MODES[@]}"; do
        RUN_COUNT=$(( RUN_COUNT + 1 ))
        session_dir="benchmark/results/${nickname}/${mode}"

        # Skip if a usable session already exists (unless FORCE=1). "Usable" means
        # one of its session_*.jsonl files reached at least COMPLETE_TURNS turns.
        # A turn threshold (not just "has a summary record") is used because 5-turn
        # smoke runs and api_error stubs still write summaries, while a long but
        # interrupted run may have none. Default 50 keeps real runs, re-runs stubs.
        if [[ "${FORCE:-0}" != "1" ]]; then
            max_turns_seen=0
            for sf in "${session_dir}"/session_*.jsonl; do
                [[ -f "$sf" ]] || continue
                t=$(grep -c '"type": *"turn"' "$sf" 2>/dev/null || echo 0)
                (( t > max_turns_seen )) && max_turns_seen=$t
            done
            if (( max_turns_seen >= ${COMPLETE_TURNS:-50} )); then
                echo "--- Run ${RUN_COUNT}/${TOTAL_RUNS} | SKIP (have ${max_turns_seen} turns): ${nickname}/${mode} ---"
                echo ""
                continue
            fi
        fi

        # Build the command as an array so model flag is cleanly optional.
        cmd=(
            uv run zork-harness
            --game zork1
            --backend "$backend"
            --max-turns "$MAX_TURNS"
            --map-mode "$mode"
            --session-dir "$session_dir"
        )
        if [[ -n "$model" ]]; then
            cmd+=(--model "$model")
        fi
        if [[ "$thinking" == "1" ]]; then
            cmd+=(--thinking)
        fi

        mkdir -p "$session_dir"

        echo "--- Run ${RUN_COUNT}/${TOTAL_RUNS} | $(date '+%Y-%m-%d %H:%M:%S') ---"
        echo "    model    : ${nickname}"
        echo "    backend  : ${backend}"
        echo "    thinking : $([[ "$thinking" == "1" ]] && echo on || echo off)"
        echo "    map-mode : ${mode}"
        echo "    session  : ${session_dir}"
        echo "    log      : ${session_dir}/run.log"
        echo ""

        if ! PYTHONUNBUFFERED=1 "${cmd[@]}" 2>&1 | tee "${session_dir}/run.log"; then
            echo "    *** Run failed, retrying once after 30s ***"
            sleep 30
            if ! PYTHONUNBUFFERED=1 "${cmd[@]}" 2>&1 | tee "${session_dir}/run_retry.log"; then
                echo "    *** Retry also failed, skipping ***"
                FAILED_RUNS+=("${nickname}/${mode}")
            fi
        fi

        echo ""
    done
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
ELAPSED_MIN=$(( ELAPSED / 60 ))
ELAPSED_SEC=$(( ELAPSED % 60 ))

echo "=== Benchmark complete ==="
echo "    Total runs   : ${TOTAL_RUNS}"
echo "    Failed runs  : ${#FAILED_RUNS[@]}"
echo "    Elapsed time : ${ELAPSED_MIN}m ${ELAPSED_SEC}s"
echo "    Results in   : ${PROJECT_ROOT}/benchmark/results/"
if [[ ${#FAILED_RUNS[@]} -gt 0 ]]; then
    echo ""
    echo "    Failed:"
    for fr in "${FAILED_RUNS[@]}"; do
        echo "      - ${fr}"
    done
fi
