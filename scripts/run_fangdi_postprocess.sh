#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_fangdi_postprocess.sh [options]

Options:
  --date YYYY-MM-DD         Run date. Defaults to today.
  --results-file PATH       Raw fangdi jsonl. Defaults to /root/fangdi-data/var/fangdi-count-results.jsonl
  --data-root PATH          Data root for archived raw files. Defaults to /root/fangdi-data/data
  --output-root PATH        Output root for normalized/metrics/report files. Defaults to /root/fangdi-data/output
  --python PATH             Python interpreter to use. Defaults to <repo>/.venv/bin/python, fallback python3
  --skip-cards              Skip PNG card rendering even if matplotlib is installed
  -h, --help                Show this help

Examples:
  scripts/run_fangdi_postprocess.sh
  scripts/run_fangdi_postprocess.sh --date 2026-03-17
  scripts/run_fangdi_postprocess.sh --results-file /tmp/fangdi-count-results.jsonl --output-root /tmp/fangdi-output
EOF
}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DATE="$(date +%F)"
RESULTS_FILE="/root/fangdi-data/var/fangdi-count-results.jsonl"
DATA_ROOT="/root/fangdi-data/data"
OUTPUT_ROOT="/root/fangdi-data/output"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
SKIP_CARDS="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      RUN_DATE="$2"
      shift 2
      ;;
    --results-file)
      RESULTS_FILE="$2"
      shift 2
      ;;
    --data-root)
      DATA_ROOT="$2"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --skip-cards)
      SKIP_CARDS="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

if [[ ! -f "${RESULTS_FILE}" ]]; then
  echo "Results file not found: ${RESULTS_FILE}" >&2
  exit 1
fi

RAW_DIR="${DATA_ROOT}/raw/fangdi/${RUN_DATE}"
NORMALIZED_DIR="${OUTPUT_ROOT}/normalized"
METRICS_DIR="${OUTPUT_ROOT}/metrics"
REPORT_DIR="${OUTPUT_ROOT}/fangdi/${RUN_DATE}"

mkdir -p "${RAW_DIR}" "${NORMALIZED_DIR}" "${METRICS_DIR}" "${REPORT_DIR}"

RAW_ARCHIVE="${RAW_DIR}/results.jsonl"
cp "${RESULTS_FILE}" "${RAW_ARCHIVE}"

DAILY_COUNTS_CSV="${NORMALIZED_DIR}/fangdi_daily_counts_${RUN_DATE}.csv"
DAILY_FAILURES_CSV="${NORMALIZED_DIR}/fangdi_daily_failures_${RUN_DATE}.csv"
DAILY_SUMMARY_JSON="${NORMALIZED_DIR}/fangdi_daily_summary_${RUN_DATE}.json"

PLATE_METRICS_CSV="${METRICS_DIR}/fangdi_plate_metrics_${RUN_DATE}.csv"
DISTRICT_METRICS_CSV="${METRICS_DIR}/fangdi_district_metrics_${RUN_DATE}.csv"
PLATE_HISTORY_CSV="${METRICS_DIR}/fangdi_plate_history_${RUN_DATE}.csv"
DISTRICT_HISTORY_CSV="${METRICS_DIR}/fangdi_district_history_${RUN_DATE}.csv"

INSIGHTS_JSON="${REPORT_DIR}/insights.json"
HISTORY_SUMMARY_JSON="${REPORT_DIR}/history_summary.json"
HEADLINES_MD="${REPORT_DIR}/headline_candidates.md"
CAPTION_MD="${REPORT_DIR}/caption_draft.md"
CARDS_DIR="${REPORT_DIR}/cards"
FULL_TABLE_CARDS_DIR="${REPORT_DIR}/cards"

echo "[fangdi] normalize raw results"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/normalize_fangdi_results.py" \
  "${RAW_ARCHIVE}" \
  "${DAILY_COUNTS_CSV}" \
  --failures-csv "${DAILY_FAILURES_CSV}" \
  --summary-json "${DAILY_SUMMARY_JSON}" \
  --run-date "${RUN_DATE}"

PREVIOUS_DAILY_COUNTS=""
if [[ -d "${NORMALIZED_DIR}" ]]; then
  while IFS= read -r file; do
    base="$(basename "${file}")"
    if [[ "${base}" != "fangdi_daily_counts_${RUN_DATE}.csv" ]]; then
      PREVIOUS_DAILY_COUNTS="${file}"
    fi
  done < <(find "${NORMALIZED_DIR}" -maxdepth 1 -type f -name 'fangdi_daily_counts_*.csv' | sort)
fi

echo "[fangdi] build daily metrics"
DAILY_ARGS=(
  "${PROJECT_ROOT}/scripts/analyze_fangdi_daily.py"
  "${DAILY_COUNTS_CSV}"
  "${PLATE_METRICS_CSV}"
  "${DISTRICT_METRICS_CSV}"
  "${INSIGHTS_JSON}"
  --normalized-summary-json "${DAILY_SUMMARY_JSON}"
)
if [[ -n "${PREVIOUS_DAILY_COUNTS}" ]]; then
  DAILY_ARGS+=(--previous-daily-counts "${PREVIOUS_DAILY_COUNTS}")
fi
"${PYTHON_BIN}" "${DAILY_ARGS[@]}"

echo "[fangdi] build history comparison"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/analyze_fangdi_history.py" \
  "${PLATE_METRICS_CSV}" \
  "${DISTRICT_METRICS_CSV}" \
  "${PLATE_HISTORY_CSV}" \
  "${DISTRICT_HISTORY_CSV}" \
  "${HISTORY_SUMMARY_JSON}" \
  --plate-history-dir "${METRICS_DIR}" \
  --district-history-dir "${METRICS_DIR}"

echo "[fangdi] render copy draft"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/render_fangdi_caption.py" \
  "${INSIGHTS_JSON}" \
  "${PLATE_METRICS_CSV}" \
  "${DISTRICT_METRICS_CSV}" \
  "${HEADLINES_MD}" \
  "${CAPTION_MD}"

if [[ "${SKIP_CARDS}" == "1" ]]; then
  echo "[fangdi] skip cards by flag"
else
  if "${PYTHON_BIN}" -c "import matplotlib" >/dev/null 2>&1; then
    echo "[fangdi] render cards"
    "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/render_fangdi_cards.py" \
      "${PLATE_METRICS_CSV}" \
      "${DISTRICT_METRICS_CSV}" \
      "${INSIGHTS_JSON}" \
      "${CARDS_DIR}"
    echo "[fangdi] render full table cards"
    "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/render_fangdi_full_table_cards.py" \
      "${PLATE_METRICS_CSV}" \
      "${FULL_TABLE_CARDS_DIR}"
  else
    echo "[fangdi] matplotlib not installed, skip cards"
  fi
fi

cat <<EOF
[fangdi] postprocess done
run_date=${RUN_DATE}
raw_archive=${RAW_ARCHIVE}
daily_counts_csv=${DAILY_COUNTS_CSV}
daily_failures_csv=${DAILY_FAILURES_CSV}
plate_metrics_csv=${PLATE_METRICS_CSV}
district_metrics_csv=${DISTRICT_METRICS_CSV}
plate_history_csv=${PLATE_HISTORY_CSV}
district_history_csv=${DISTRICT_HISTORY_CSV}
insights_json=${INSIGHTS_JSON}
history_summary_json=${HISTORY_SUMMARY_JSON}
headline_candidates_md=${HEADLINES_MD}
caption_draft_md=${CAPTION_MD}
cards_dir=${CARDS_DIR}
EOF
