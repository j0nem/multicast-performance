#!/bin/bash
# orchestrator.sh - Orchestrate distributed QUIC tests across multiple VMs
# Usage: ./orchestrator.sh <config_file>

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <config_file>"
    echo ""
    echo "Config file format (YAML-like):"
    echo "server_vm: user@server-ip"
    echo "client_vms:"
    echo "  - user@client1-ip"
    echo "  - user@client2-ip"
    echo "  - user@client3-ip"
    echo "test_name: multicast_test"
    echo "server_binary: /path/to/server"
    echo "client_binary: /path/to/client"
    echo "server_args: -p 4433"
    echo "client_args: -h SERVER_IP -p 4433"
    echo "test_duration: 60"
    exit 1
fi

CONFIG_FILE=$1

# Parse config file (simple bash parsing)
SERVER_VM=$(grep "^server_vm:" "$CONFIG_FILE" | cut -d: -f2- | xargs)
CLIENT_VMS=($(grep -A10 "^client_vms:" "$CONFIG_FILE" | grep "^  -" | sed 's/^  - //'))
CLIENTS_PER_VM=$(grep "^clients_per_vm:" "$CONFIG_FILE" | cut -d: -f2- | xargs || echo "1")
TEST_NAME=$(grep "^test_name:" "$CONFIG_FILE" | cut -d: -f2- | xargs)
SERVER_BIN=$(grep "^server_binary:" "$CONFIG_FILE" | cut -d: -f2- | xargs)
CLIENT_BIN=$(grep "^client_binary:" "$CONFIG_FILE" | cut -d: -f2- | xargs)
SERVER_ARGS=$(grep "^server_args:" "$CONFIG_FILE" | cut -d: -f2- | xargs)
CLIENT_ARGS=$(grep "^client_args:" "$CONFIG_FILE" | cut -d: -f2- | xargs)
ITERATIONS=$(grep "^iterations:" "$CONFIG_FILE" | cut -d: -f2- | xargs || echo "1")

# Check if this is an iteration run (second parameter)
CURRENT_ITERATION=${2:-1}

echo "=========================================="
echo "QUIC Distributed Test Orchestration"
echo "=========================================="
echo ""
echo "Test: $TEST_NAME"
echo "Server: $SERVER_VM"
echo "Clients: ${CLIENT_VMS[@]}"
echo "Clients per VM: $CLIENTS_PER_VM"
echo "Total Clients: $((${#CLIENT_VMS[@]} * CLIENTS_PER_VM))"
if [ "$ITERATIONS" -gt 1 ]; then
    echo "Iteration: $CURRENT_ITERATION / $ITERATIONS"
fi
echo ""
echo "Press Ctrl+C to stop the test"
echo ""

# Create local results directory
if [ "$ITERATIONS" -gt 1 ]; then
    LOCAL_RESULTS="results/${TEST_NAME}_iter${CURRENT_ITERATION}_$(date +%Y%m%d_%H%M%S)"
else
    LOCAL_RESULTS="results/${TEST_NAME}_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$LOCAL_RESULTS"

# Save configuration
cp "$CONFIG_FILE" "$LOCAL_RESULTS/test_config.yaml"

echo "Step 1: Uploading scripts to all VMs..."

# Upload scripts to all VMs
for vm in $SERVER_VM "${CLIENT_VMS[@]}"; do
    echo "  Uploading to $vm..."
    ssh "$vm" "mkdir -p ~/quic_tests"
    scp server_measure.sh client_measure.sh analyze_results.sh "$vm:~/quic_tests/" > /dev/null
    ssh "$vm" "chmod +x ~/quic_tests/*.sh"
done

echo "Done."
echo ""

# Trap to cleanup on exit
trap cleanup SIGINT SIGTERM EXIT

# Get server IP from SERVER_VM
SERVER_IP=$(echo $SERVER_VM | cut -d@ -f2)

# Replace SERVER_IP placeholder in client args
CLIENT_ARGS="${CLIENT_ARGS//SERVER_IP/$SERVER_IP}"

# Cleanup function
cleanup() {
    echo ""
    echo "=========================================="
    echo "Stopping all processes..."
    echo "=========================================="
    
    # Kill the status check if it's running
    if [ -n "$STATUS_PID" ]; then
        kill $STATUS_PID 2>/dev/null || true
    fi
    
    # Stop all clients
    echo "Stopping clients..."
    for i in "${!CLIENT_VMS[@]}"; do
        client="${CLIENT_VMS[$i]}"
        echo "  Stopping clients on $client..."
        ssh "$client" "pkill -f client_measure.sh 2>/dev/null; pkill -f '$CLIENT_BIN' 2>/dev/null; exit 0" || true
    done
    
    # Stop server - send interrupt signal to server_measure.sh which will handle cleanup
    echo "Stopping server..."
    ssh "$SERVER_VM" "pkill -SIGINT -f 'server_measure.sh.*$TEST_NAME' 2>/dev/null; exit 0" || true
    
    # Wait for graceful shutdown
    echo "Waiting for processes to finish..."
    sleep 5
    
    # Force kill any remaining processes
    ssh "$SERVER_VM" "pkill -9 -f '$SERVER_BIN' 2>/dev/null; exit 0" || true
    for i in "${!CLIENT_VMS[@]}"; do
        client="${CLIENT_VMS[$i]}"
        ssh "$client" "pkill -9 -f '$CLIENT_BIN' 2>/dev/null; exit 0" || true
    done
    
    sleep 2
    
    # Collect results
    collect_results
    
    echo ""
    echo "=========================================="
    echo "Test Complete!"
    echo "=========================================="
    echo ""
    echo "Results saved to: $LOCAL_RESULTS"
    echo "Summary: $LOCAL_RESULTS/test_summary.txt"
    echo ""
    echo "To view the summary:"
    echo "  cat $LOCAL_RESULTS/test_summary.txt"
    echo ""
    
    exit 0
}

# Main execution
run_single_test() {
    # All the test logic is already above
    :
}

# Run test(s)
if [ "$CURRENT_ITERATION" -eq 1 ] && [ "$ITERATIONS" -gt 1 ]; then
    # This is the first call and we need to run multiple iterations
    echo "Running $ITERATIONS iterations..."
    echo ""
    
    for iter in $(seq 1 $ITERATIONS); do
        echo "========================================"
        echo "Starting iteration $iter of $ITERATIONS"
        echo "========================================"
        
        # Run this script again with iteration number
        "$0" "$CONFIG_FILE" "$iter"
        
        if [ $? -ne 0 ]; then
            echo "Iteration $iter failed!"
            exit 1
        fi
        
        # Wait between iterations
        if [ $iter -lt $ITERATIONS ]; then
            echo ""
            echo "Waiting 30 seconds before next iteration..."
            sleep 30
        fi
    done
    
    echo ""
    echo "========================================"
    echo "All $ITERATIONS iterations complete!"
    echo "========================================"
    echo ""
    echo "Results stored in: results/${TEST_NAME}_iter*"
    echo ""
    
    exit 0
fi

# If we get here, run a single test (either standalone or as part of iterations)
# The test logic is already in the script above

trap cleanup SIGINT SIGTERM

collect_results() {
    echo ""
    echo "Collecting results..."
    
    # Wait a bit for processes to finish writing
    sleep 2
    
    # Collect server results
    echo "  Collecting from server..."
    REMOTE_SERVER_DIR=$(ssh "$SERVER_VM" "ls -dt ~/quic_tests/results/${TEST_NAME}_* 2>/dev/null | head -1" || echo "")
    if [ -n "$REMOTE_SERVER_DIR" ]; then
        mkdir -p "$LOCAL_RESULTS/server"
        scp -r "$SERVER_VM:$REMOTE_SERVER_DIR/*" "$LOCAL_RESULTS/server/" > /dev/null 2>&1 || {
            echo "  Warning: Failed to collect some server results"
        }
    else
        echo "  Warning: No server results found"
    fi
    
    # Collect client results
    for i in "${!CLIENT_VMS[@]}"; do
        client="${CLIENT_VMS[$i]}"
        echo "  Collecting from client VM $i..."
        REMOTE_CLIENT_DIR=$(ssh "$client" "ls -dt ~/quic_tests/results/${TEST_NAME}_client${i}_* 2>/dev/null | head -1" || echo "")
        if [ -n "$REMOTE_CLIENT_DIR" ]; then
            mkdir -p "$LOCAL_RESULTS/client_vm${i}"
            scp -r "$client:$REMOTE_CLIENT_DIR/*" "$LOCAL_RESULTS/client_vm${i}/" > /dev/null 2>&1 || {
                echo "  Warning: Failed to collect some results from client VM $i"
            }
        else
            echo "  Warning: No results found for client VM $i"
        fi
    done
    
    echo "Done."
    
    # Generate analysis
    echo ""
    echo "Generating analysis..."
    if [ -d "$LOCAL_RESULTS/server" ] && [ -f "./analyze_results.sh" ]; then
        ./analyze_results.sh "$LOCAL_RESULTS/server" > "$LOCAL_RESULTS/server_analysis.txt" 2>&1 || {
            echo "  Warning: Analysis generation failed"
        }
    fi
    
    # Generate combined summary
    cat > "$LOCAL_RESULTS/test_summary.txt" <<EOF
========================================
QUIC Distributed Test Summary
========================================

Test Name: $TEST_NAME
Test Date: $(date)
Number of Client VMs: ${#CLIENT_VMS[@]}
Clients per VM: $CLIENTS_PER_VM
Total Clients: $((${#CLIENT_VMS[@]} * CLIENTS_PER_VM))

Server: $SERVER_VM
Clients: ${CLIENT_VMS[@]}

========================================
Server Results
========================================

EOF
    
    if [ -f "$LOCAL_RESULTS/server_analysis.txt" ]; then
        cat "$LOCAL_RESULTS/server_analysis.txt" >> "$LOCAL_RESULTS/test_summary.txt"
    else
        echo "No server analysis available" >> "$LOCAL_RESULTS/test_summary.txt"
    fi
    
    # Add client summaries if available
    for i in "${!CLIENT_VMS[@]}"; do
        if [ -f "$LOCAL_RESULTS/client_vm${i}/test_config.txt" ]; then
            echo "" >> "$LOCAL_RESULTS/test_summary.txt"
            echo "Client VM $i Results (${CLIENT_VMS[$i]})" >> "$LOCAL_RESULTS/test_summary.txt"
            echo "----------------------------------------" >> "$LOCAL_RESULTS/test_summary.txt"
            cat "$LOCAL_RESULTS/client_vm${i}/test_config.txt" >> "$LOCAL_RESULTS/test_summary.txt"
        fi
    done
}

echo "Step 2: Starting server on $SERVER_VM..."
ssh "$SERVER_VM" "cd ~/quic_tests && nohup ./server_measure.sh $SERVER_BIN $TEST_NAME $SERVER_ARGS > server_orchestrator.log 2>&1 &"
echo "Waiting for server to initialize..."
sleep 5

# Verify server is running - try multiple times
SERVER_RUNNING=0
for i in {1..3}; do
    SERVER_RUNNING=$(ssh "$SERVER_VM" "pgrep -f '$SERVER_BIN' 2>/dev/null | wc -l" || echo "0")
    
    # Ensure it's a valid number
    if ! [[ "$SERVER_RUNNING" =~ ^[0-9]+$ ]]; then
        SERVER_RUNNING=0
    fi
    
    if [ "$SERVER_RUNNING" -gt 0 ]; then
        break
    fi
    
    if [ $i -lt 3 ]; then
        echo "  Server not detected yet, waiting..."
        sleep 3
    fi
done

if [ "$SERVER_RUNNING" -gt 0 ]; then
    echo "Server started successfully (found $SERVER_RUNNING process(es))"
else
    echo "Warning: Server may not have started properly"
    echo "Check server log: ssh $SERVER_VM 'cat ~/quic_tests/server_orchestrator.log'"
fi
echo ""

echo "Step 3: Starting clients..."
for i in "${!CLIENT_VMS[@]}"; do
    client="${CLIENT_VMS[$i]}"
    echo "  Starting $CLIENTS_PER_VM client(s) on $client..."
    # Use ssh without backgrounding to ensure we see any errors
    ssh "$client" "cd ~/quic_tests && nohup ./client_measure.sh $CLIENT_BIN ${TEST_NAME}_client${i} $CLIENTS_PER_VM $CLIENT_ARGS > client_orchestrator.log 2>&1 &" || {
        echo "  Warning: Failed to start clients on $client"
    }
    sleep 2
done

echo "All clients started."
echo ""

echo "=========================================="
echo "Test is running..."
echo "Press Ctrl+C to stop the test"
echo "=========================================="
echo ""

# Show status updates
status_check() {
    local count=0
    while true; do
        sleep 10
        count=$((count + 1))
        
        # Check if server is still running every 10 seconds
        local server_count=$(ssh "$SERVER_VM" "pgrep -f '$SERVER_BIN' 2>/dev/null | wc -l" 2>/dev/null || echo "0")
        
        # Ensure it's a valid number
        if ! [[ "$server_count" =~ ^[0-9]+$ ]]; then
            server_count=0
        fi
        
        if [ "$server_count" -eq 0 ]; then
            echo ""
            echo "Server process has stopped."
            return 1
        fi
        
        # Print status every 30 seconds
        if [ $((count % 3)) -eq 0 ]; then
            echo "Status check: Server running, test duration: $((count * 10))s"
        fi
    done
}

# Run status check in a way that can be interrupted
status_check &
STATUS_PID=$!

# Wait for status check to exit or for user interrupt
wait $STATUS_PID 2>/dev/null || true

# If we reach here, either server stopped or user pressed Ctrl+C
echo ""
echo "Test processes have completed or were interrupted."
cleanup
