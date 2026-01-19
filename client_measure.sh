#!/bin/bash
# client_measure.sh - Run QUIC client(s) with monitoring
# Usage: ./client_measure.sh <client_binary> <test_name> <num_clients> [client_args...]

set -e

if [ $# -lt 3 ]; then
    echo "Usage: $0 <client_binary> <test_name> <num_clients> [client_args...]"
    echo "Example: $0 ./picoquic_client multicast_test 3 -h server_ip -p 4433"
    exit 1
fi

CLIENT_BIN=$1
TEST_NAME=$2
NUM_CLIENTS=$3
shift 3
CLIENT_ARGS="$@"

# Create results directory
RESULTS_DIR="results/${TEST_NAME}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Detect network interface
INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
echo "Using network interface: $INTERFACE"

# Log test configuration
cat > "$RESULTS_DIR/test_config.txt" <<EOF
Test Name: $TEST_NAME
Client Binary: $CLIENT_BIN
Number of Clients: $NUM_CLIENTS
Client Args: $CLIENT_ARGS
Network Interface: $INTERFACE
Start Time: $(date)
Hostname: $(hostname)
EOF

echo "Starting client monitoring for test: $TEST_NAME"
echo "Number of clients: $NUM_CLIENTS"
echo "Results will be saved to: $RESULTS_DIR"

# Start network statistics monitoring
sar -n DEV 1 > "$RESULTS_DIR/network_stats.log" 2>&1 &
SAR_PID=$!

# Array to store client PIDs
CLIENT_PIDS=()
ACTUAL_CLIENT_PIDS=()

# Start multiple client instances
echo "Starting $NUM_CLIENTS client instances..."
for i in $(seq 1 $NUM_CLIENTS); do
    echo "  Starting client $i/$NUM_CLIENTS..."
    mkdir -p "$RESULTS_DIR/client_$i"
    
    /usr/bin/time -v "$CLIENT_BIN" $CLIENT_ARGS \
        > "$RESULTS_DIR/client_$i/stdout.log" \
        2> "$RESULTS_DIR/client_$i/time.log" &
    
    TIME_PID=$!
    CLIENT_PIDS+=($TIME_PID)
    
    # Wait a bit and find the actual client process (child of time)
    sleep 1
    ACTUAL_CLIENT_PID=$(pgrep -P $TIME_PID 2>/dev/null | head -1)
    if [ -n "$ACTUAL_CLIENT_PID" ]; then
        ACTUAL_CLIENT_PIDS+=($ACTUAL_CLIENT_PID)
        echo "$ACTUAL_CLIENT_PID" > "$RESULTS_DIR/client_$i/client_pid"
    fi
    
    # Small delay between client starts to avoid thundering herd
    sleep 0.5
done

echo "All $NUM_CLIENTS clients started"
echo "Time wrapper PIDs: ${CLIENT_PIDS[@]}"
echo "Actual client PIDs: ${ACTUAL_CLIENT_PIDS[@]}"

# Trap for cleanup
cleanup() {
    echo ""
    echo "Stopping clients..."

    # Prevent recursive calls
    trap - SIGINT SIGTERM

    # Stop monitoring
    kill $SAR_PID 2>/dev/null || true
    sleep 1
    
    for i in $(seq 1 $NUM_CLIENTS); do
        local SAVED_CLIENT_PID=""
        local SAVED_TIME_PID=""

        if [ -f "$RESULTS_DIR/client_$i/client_pid" ]; then
            SAVED_CLIENT_PID=$(cat "$RESULTS_DIR/client_$i/client_pid")
        fi
        
        # Stop the actual server process first if it's running
        if [ -n "$SAVED_CLIENT_PID" ] && kill -0 "$SAVED_CLIENT_PID" 2>/dev/null; then
            echo "Stopping client process (PID: $SAVED_CLIENT_PID)..."
            kill -TERM "$SAVED_CLIENT_PID" 2>/dev/null || true
            
            # Wait up to 5 seconds for graceful shutdown
            local stopped=0
            for i in {1..5}; do
                if ! kill -0 "$SAVED_CLIENT_PID" 2>/dev/null; then
                    echo "Client stopped gracefully"
                    stopped=1
                    break
                fi
                sleep 1
            done
            
            # Force kill if still running
            if [ $stopped -eq 0 ] && kill -0 "$SAVED_CLIENT_PID" 2>/dev/null; then
                echo "Force killing client..."
                kill -KILL "$SAVED_CLIENT_PID" 2>/dev/null || true
            fi
        fi      
        
        # Also kill by binary name as a safety measure (but not ourselves!)
        pkill -f "$CLIENT_BIN" 2>/dev/null || true
    done

    # Kill all client time processes
    for pid in "${CLIENT_PIDS[@]}"; do
        kill -TERM $pid 2>/dev/null || true
    done
    
    sleep 2
    
    # Force kill any remaining
    for pid in "${CLIENT_PIDS[@]}"; do
        kill -KILL $pid 2>/dev/null || true
    done
    
    echo "All clients stopped."

    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for all client processes to complete
echo "Waiting for clients to finish (press Ctrl+C to stop)..."
for pid in "${CLIENT_PIDS[@]}"; do
    wait $pid 2>/dev/null || true
done

echo "All clients finished naturally"

# Stop monitoring
kill $SAR_PID 2>/dev/null || true
sleep 1

# Save final statistics
cat >> "$RESULTS_DIR/test_config.txt" <<EOF
End Time: $(date)
EOF

# Aggregate client exit codes
echo "" >> "$RESULTS_DIR/test_config.txt"
echo "Client Exit Codes:" >> "$RESULTS_DIR/test_config.txt"
for i in $(seq 1 $NUM_CLIENTS); do
    if [ -f "$RESULTS_DIR/client_$i/time.log" ]; then
        echo "  Client $i: Check time.log for details" >> "$RESULTS_DIR/test_config.txt"
    fi
done

# Save system info
cat > "$RESULTS_DIR/system_info.txt" <<EOF
=== System Information ===
$(uname -a)

=== CPU Info ===
$(lscpu)

=== Memory Info ===
$(free -h)

=== Network Interfaces ===
$(ip addr)
EOF

echo "Results saved to: $RESULTS_DIR"
echo "Done."

cleanup