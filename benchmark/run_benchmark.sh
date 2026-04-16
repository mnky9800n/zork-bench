#!/usr/bin/env bash
# benchmark/run_benchmark.sh
#
# Runs 9 configurations of zork-harness (3 models x 3 map modes) sequentially.
# Results land in benchmark/results/<nickname>/<mode>/.
#
# Override turn count for quick tests:
#   MAX_TURNS=5 bash benchmark/run_benchmark.sh

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve project root from script location and cd there
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

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
)
BACKENDS=(
    "fireworks"
    "fireworks"
    "fireworks"
    "fireworks"
    "fireworks"
    "fireworks"
)
# Empty string means omit --model flag (uses backend default).
MODELS=(
    "accounts/fireworks/models/gpt-oss-120b"
    "accounts/fireworks/models/minimax-m2p7"
    "accounts/fireworks/models/glm-5p1"
    "accounts/fireworks/models/kimi-k2p5"
    "accounts/fireworks/models/deepseek-v3p2"
    "accounts/fireworks/models/cogito-671b-v2-p1"
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

if [[ -z "${FIREWORKS_API_KEY:-}" ]]; then
    echo "ERROR: FIREWORKS_API_KEY is not set." >&2
    exit 1
fi
echo "  [ok] FIREWORKS_API_KEY is set"

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

    for mode in "${MAP_MODES[@]}"; do
        RUN_COUNT=$(( RUN_COUNT + 1 ))
        session_dir="benchmark/results/${nickname}/${mode}"

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

        mkdir -p "$session_dir"

        echo "--- Run ${RUN_COUNT}/${TOTAL_RUNS} | $(date '+%Y-%m-%d %H:%M:%S') ---"
        echo "    model    : ${nickname}"
        echo "    backend  : ${backend}"
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
