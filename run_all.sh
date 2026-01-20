#!/bin/bash
# run_all.sh - Run tests for all config files in the current directory
# Usage: ./run_all.sh <config_folder>

COMMAND="./orchestrator.sh"
FOLDER="$1"

if [[ ${FOLDER: -1} != "/" ]]; then
    FOLDER="${FOLDER}/"
fi

echo "=================================================================="
echo "Run test scenarios for all configurations in ${FOLDER}*conf..."
echo "=================================================================="

# Iterate over all files matching *conf in the specified directory
for file in ${FOLDER}*conf; do
    if [[ -f $file ]] && [[ $file != *.conf.example ]]; then
        $COMMAND "$file"
        echo "Wait 30 seconds until the next test..."
        sleep 30
    fi
done