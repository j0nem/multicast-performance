#!/bin/bash

# Check if correct number of arguments is given
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <results_folder>"
    exit 1
fi

RESULTS_FOLDER=$1
SERVER_FOLDER_NAME="server"
COMMAND="python3 analyze_results.py"

if [[ ${RESULTS_FOLDER: -1} != "/" ]]; then
    RESULTS_FOLDER="${RESULTS_FOLDER}/"
fi

# Loop through each subfolder in the main folder
for SUBFOLDER in "$RESULTS_FOLDER"*; do
    if [ -d "$SUBFOLDER" ]; then
        # Check if the sub-subfolder exists
        if [ -d "$SUBFOLDER/$SERVER_FOLDER_NAME" ]; then
            echo "Generating results to: "$SUBFOLDER/server_analysis.txt""
            # Execute the specified command
            $COMMAND "$SUBFOLDER/$SERVER_FOLDER_NAME" > "$SUBFOLDER/server_analysis.txt"
        fi
    fi
done