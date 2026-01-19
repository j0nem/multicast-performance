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

# Start multiple client instances
echo "Starting $NUM_CLIENTS client instances..."
for i in $(seq 1 $NUM_CLIENTS); do
    echo "  Starting client $i/$NUM_CLIENTS..."
    mkdir -p "$RESULTS_DIR/client_$i"
    
    /usr/bin/time -v "$CLIENT_BIN" $CLIENT_ARGS \
        > "$RESULTS_DIR/client_$i/stdout.log" \
        2> "$RESULTS_DIR/client_$i/time.log" &
    
    CLIENT_PIDS+=($!)
    
    # Small delay between client starts to avoid thundering herd
    sleep 0.5
done

echo "All $NUM_CLIENTS clients started with PIDs: ${CLIENT_PIDS[@]}"

# Trap for cleanup
cleanup() {
    echo ""
    echo "Stopping clients..."
    
    # Kill all client processes
    for pid in "${CLIENT_PIDS[@]}"; do
        kill -TERM $pid 2>/dev/null || true
    done
    
    sleep 2
    
    # Force kill any remaining
    for pid in "${CLIENT_PIDS[@]}"; do
        kill -KILL $pid 2>/dev/null || true
    done
    
    # Stop monitoring
    kill $SAR_PID 2>/dev/null || true
    sleep 1
    
    echo "All clients stopped."
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
