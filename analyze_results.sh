#!/bin/bash
# analyze_results.sh - Analyze measurement results
# Usage: ./analyze_results.sh <results_directory>

if [ $# -lt 1 ]; then
    echo "Usage: $0 <results_directory>"
    exit 1
fi

RESULTS_DIR=$1

if [ ! -d "$RESULTS_DIR" ]; then
    echo "Error: Directory $RESULTS_DIR not found"
    exit 1
fi

echo "========================================"
echo "QUIC Performance Test Results Analysis"
echo "========================================"
echo ""

# Test configuration
if [ -f "$RESULTS_DIR/test_config.txt" ]; then
    echo "=== Test Configuration ==="
    cat "$RESULTS_DIR/test_config.txt"
    echo ""
fi

# Server resource usage (from /usr/bin/time)
if [ -f "$RESULTS_DIR/server_time.log" ]; then
    echo "=== Server Resource Usage Summary ==="
    echo ""
    grep -E "User time|System time|Percent of CPU|Maximum resident set size|Voluntary context switches|Involuntary context switches" \
        "$RESULTS_DIR/server_time.log" || echo "No time statistics found"
    echo ""
fi

# Client resource usage
if [ -f "$RESULTS_DIR/client_time.log" ]; then
    echo "=== Client Resource Usage Summary ==="
    echo ""
    grep -E "User time|System time|Percent of CPU|Maximum resident set size" \
        "$RESULTS_DIR/client_time.log" || echo "No time statistics found"
    echo ""
fi

# CPU and Memory usage from pidstat
if [ -f "$RESULTS_DIR/pidstat.log" ]; then
    echo "=== CPU and Memory Statistics (pidstat) ==="
    echo ""
    
    # Parse pidstat output - it has three sections: CPU, Memory, and Disk I/O
    # We need to extract values carefully based on column positions
    
    # CPU usage (look for %CPU column which is typically column 8)
    avg_cpu=$(awk '
        /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ && $8 ~ /^[0-9]+\./ && NF >= 9 {
            sum += $8; count++
        }
        END {
            if (count > 0) printf "%.2f", sum/count
            else print "N/A"
        }
    ' "$RESULTS_DIR/pidstat.log")
    
    peak_cpu=$(awk '
        /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ && $8 ~ /^[0-9]+\./ && NF >= 9 {
            if ($8 > max) max = $8
        }
        END {
            if (max > 0) printf "%.2f", max
            else print "N/A"
        }
    ' "$RESULTS_DIR/pidstat.log")
    
    # Memory usage (RSS is typically in KB, look for minflt/s section)
    # RSS is in column 6 of the memory section
    avg_mem=$(awk '
        /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ && /minflt\/s/ {
            getline
            if ($6 ~ /^[0-9]+$/ && NF >= 7) {
                sum += $6; count++
            }
        }
        END {
            if (count > 0) printf "%.0f", sum/count
            else print "N/A"
        }
    ' "$RESULTS_DIR/pidstat.log")
    
    peak_mem=$(awk '
        /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ && /minflt\/s/ {
            getline
            if ($6 ~ /^[0-9]+$/ && NF >= 7) {
                if ($6 > max) max = $6
            }
        }
        END {
            if (max > 0) printf "%.0f", max
            else print "N/A"
        }
    ' "$RESULTS_DIR/pidstat.log")
    
    echo "Average CPU Usage: $avg_cpu %"
    echo "Peak CPU Usage: $peak_cpu %"
    echo ""
    echo "Average Memory (RSS): $avg_mem KB"
    echo "Peak Memory (RSS): $peak_mem KB"
    echo ""
fi

# Network statistics from packet capture
if [ -f "$RESULTS_DIR/network_capture.pcap" ]; then
    echo "=== Network Statistics (from packet capture) ==="
    echo ""
    
    # Use capinfos if available
    if command -v capinfos &> /dev/null; then
        capinfos "$RESULTS_DIR/network_capture.pcap" | grep -E "Number of packets|File size|Data size|Capture duration|Average packet rate|Average data rate"
    else
        # Fallback to basic tcpdump analysis
        echo "Packet count:"
        tcpdump -r "$RESULTS_DIR/network_capture.pcap" 2>/dev/null | wc -l
        echo ""
        echo "File size:"
        ls -lh "$RESULTS_DIR/network_capture.pcap" | awk '{print $5}'
    fi
    echo ""
    
    # Protocol distribution
    if command -v tshark &> /dev/null; then
        echo "=== Protocol Distribution ==="
        tshark -r "$RESULTS_DIR/network_capture.pcap" -q -z io,phs 2>/dev/null | head -20 || true
        echo ""
    fi
fi

# Network interface statistics from sar
if [ -f "$RESULTS_DIR/network_stats.log" ]; then
    echo "=== Network Interface Statistics (sar) ==="
    echo ""
    
    # Extract average transmission rates
    awk '/Average:/ && $2 ~ /^[a-z]/ {
        print "Interface: " $2
        print "  RX packets/s: " $3
        print "  TX packets/s: " $4
        print "  RX KB/s: " $5
        print "  TX KB/s: " $6
        print ""
    }' "$RESULTS_DIR/network_stats.log" || echo "No sar statistics found"
fi

echo "========================================"
echo "End of Analysis"
echo "========================================"
