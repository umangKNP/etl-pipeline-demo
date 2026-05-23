#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  ETL Cron Schedule — World Bank AU Employment Pipeline
#  Runs daily at 06:00 AM local time
#
#  SETUP (run once):
#    chmod +x cron/schedule.sh
#    crontab -e
#    then add the line below (adjust paths):
# ─────────────────────────────────────────────────────────────
# CRONTAB LINE (runs daily at 6am):
# 0 6 * * * /path/to/etl-pipeline-demo/cron/schedule.sh >> /path/to/etl-pipeline-demo/logs/cron.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PYTHON="python3"

mkdir -p "$LOG_DIR"

echo "──────────────────────────────────────────────"
echo "ETL run started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Project dir: $PROJECT_DIR"
echo "──────────────────────────────────────────────"

cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "Activated virtual environment"
fi

# Run the pipeline
$PYTHON src/pipeline.py \
    --config config/config.yaml \
    2>&1 | tee -a "$LOG_DIR/etl_$(date '+%Y%m%d').log"

EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    echo "ETL run SUCCESS: $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo "ETL run FAILED (exit code $EXIT_CODE): $(date '+%Y-%m-%d %H:%M:%S')"
    # Optionally send alert email:
    # echo "ETL pipeline failed at $(date)" | mail -s "ETL FAILURE" umangkochar1@gmail.com
fi

exit $EXIT_CODE
