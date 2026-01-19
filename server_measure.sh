#!/bin/bash
# server_measure.sh - Run QUIC server with comprehensive monitoring
# Usage: ./server_measure.sh <server_binary> <test_name> [server_args...]

set -e

if [ $# -lt 2 ]; then
    echo "Usage: $0 <server_binary> <test_name> [server_args...]"
    echo "Example: $0 ./picoquic_server multicast_test -p 4433"
    exit 1
fi

SERVER_BIN=$1
TEST_NAME=$2
shift 2
SERVER_ARGS="$@"

# Create results directory
RESULTS_DIR="results/${TEST_NAME}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Detect network interface (modify if needed)
INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
echo "Using network interface: $INTERFACE"

# Log test configuration
cat > "$RESULTS_DIR/test_config.txt" <<EOF
Test Name: $TEST_NAME
Server Binary: $SERVER_BIN
Server Args: $SERVER_ARGS
Network Interface: $INTERFACE
Start Time: $(date)
Hostname: $(hostname)
EOF

echo "Starting server monitoring for test: $TEST_NAME"
echo "Results will be saved to: $RESULTS_DIR"

# Start the server with time measurement
echo "Starting server: $SERVER_BIN $SERVER_ARGS"
/usr/bin/time -v "$SERVER_BIN" $SERVER_ARGS > "$RESULTS_DIR/server_stdout.log" 2> "$RESULTS_DIR/server_time.log" &
TIME_PID=$!

# Save TIME_PID immediately
echo "$TIME_PID" > "$RESULTS_DIR/time_pid"

# Wait for server to initialize
sleep 3

# Find the actual server process (child of time command)
# The time command spawns the actual server as a child process
ACTUAL_SERVER_PID=""
for i in {1..5}; do
    ACTUAL_SERVER_PID=$(pgrep -P $TIME_PID 2>/dev/null | head -1)
    if [ -n "$ACTUAL_SERVER_PID" ]; then
        break
    fi
    sleep 1
done

if [ -z "$ACTUAL_SERVER_PID" ]; then
    echo "Error: Server process not found as child of time command"
    # Check if time process still exists
    if ! kill -0 $TIME_PID 2>/dev/null; then
        echo "Error: Time wrapper process died"
    fi
    exit 1
fi

# Verify the actual server is running
if ! kill -0 $ACTUAL_SERVER_PID 2>/dev/null; then
    echo "Error: Server process exists but is not responding"
    exit 1
fi

echo "Server started successfully - time PID: $TIME_PID, actual server PID: $ACTUAL_SERVER_PID"

# Save server PID
echo "$ACTUAL_SERVER_PID" > "$RESULTS_DIR/server_pid"

# Start pidstat monitoring (CPU, memory, disk I/O) on the actual server process
echo "Starting resource monitoring..."
pidstat -t -p $ACTUAL_SERVER_PID -u -r -d 1 > "$RESULTS_DIR/pidstat.log" 2>&1 &
PIDSTAT_PID=$!

# Monitor network interface statistics
sar -n DEV 1 > "$RESULTS_DIR/network_stats.log" 2>&1 &
SAR_PID=$!

# Save initial system state
cat > "$RESULTS_DIR/system_info.txt" <<EOF
=== System Information ===
$(uname -a)

=== CPU Info ===
$(lscpu)

=== Memory Info ===
$(free -h)

=== Network Interfaces ===
$(ip addr)

=== Initial Process Info ===
$(ps aux | grep $ACTUAL_SERVER_PID | grep -v grep)
EOF

echo ""
echo "=========================================="
echo "Monitoring active. Server PID: $ACTUAL_SERVER_PID"
echo "Press Ctrl+C to stop monitoring and server"
echo "=========================================="
echo ""

# Trap to cleanup on exit
cleanup() {
    echo ""
    echo "Stopping monitoring and server..."
    
    # Prevent recursive calls
    trap - SIGINT SIGTERM
    
    # Stop monitoring processes
    kill $PIDSTAT_PID 2>/dev/null || true
    kill $SAR_PID 2>/dev/null || true
    
    # Read PIDs from files
    local SAVED_SERVER_PID=""
    local SAVED_TIME_PID=""
    
    if [ -f "$RESULTS_DIR/server_pid" ]; then
        SAVED_SERVER_PID=$(cat "$RESULTS_DIR/server_pid")
    fi
    
    if [ -f "$RESULTS_DIR/time_pid" ]; then
        SAVED_TIME_PID=$(cat "$RESULTS_DIR/time_pid")
    fi
    
    # Stop the actual server process first if it's running
    if [ -n "$SAVED_SERVER_PID" ] && kill -0 "$SAVED_SERVER_PID" 2>/dev/null; then
        echo "Stopping server process (PID: $SAVED_SERVER_PID)..."
        kill -TERM "$SAVED_SERVER_PID" 2>/dev/null || true
        
        # Wait up to 5 seconds for graceful shutdown
        local stopped=0
        for i in {1..5}; do
            if ! kill -0 "$SAVED_SERVER_PID" 2>/dev/null; then
                echo "Server stopped gracefully"
                stopped=1
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if [ $stopped -eq 0 ] && kill -0 "$SAVED_SERVER_PID" 2>/dev/null; then
            echo "Force killing server..."
            kill -KILL "$SAVED_SERVER_PID" 2>/dev/null || true
        fi
    fi
    
    # Stop the time wrapper process if it's still running
    if [ -n "$SAVED_TIME_PID" ] && kill -0 "$SAVED_TIME_PID" 2>/dev/null; then
        kill -TERM "$SAVED_TIME_PID" 2>/dev/null || true
        sleep 1
        kill -KILL "$SAVED_TIME_PID" 2>/dev/null || true
    fi
    
    # Also kill by binary name as a safety measure (but not ourselves!)
    pkill -f "$SERVER_BIN" 2>/dev/null || true
    
    # Save final statistics
    echo "End Time: $(date)" >> "$RESULTS_DIR/test_config.txt"
    
    # Generate summary
    echo "Generating summary..."
    if [ -f "./analyze_results.py" ]; then
        python3 ./analyze_results.py "$RESULTS_DIR" > "$RESULTS_DIR/summary.txt" 2>&1 || true
    else
        echo "Warning: analyze_results.py not found" > "$RESULTS_DIR/summary.txt"
    fi
    
    echo "Results saved to: $RESULTS_DIR"
    echo "Done."

    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for the time wrapper process (not the server directly)
# This prevents the script from exiting while the server is running
echo ""
echo "=========================================="
echo "Server is running. Press Ctrl+C to stop."
echo "=========================================="
echo ""

wait $TIME_PID 2>/dev/null || true

# If we reach here, the time process (and thus the server) has exited
echo ""
echo "Server process has exited"

cleanup
