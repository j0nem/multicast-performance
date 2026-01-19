# QUIC Multicast Performance Measurement

---

This is a set of tools to measure the performance of the Picoquic multicast extension:  
https://github.com/j0nem/picoquic-multicast

---

## Prerequisites

### Install Required Tools on All VMs

Setup all tools + the full picoquic-multicast project, build it, and get example files on Debian/Ubuntu:

```bash
# Please have a look what that script does before executing it
./setup_picoquic_multicast.sh
```

Install only the tools for the measurements:

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y sysstat tcpdump tshark ssh

# RHEL/CentOS
sudo yum install -y sysstat tcpdump wireshark-cli openssh-clients

# Enable sar data collection
sudo systemctl enable sysstat
sudo systemctl start sysstat
```

### On host system

For the `analyze_results.py` script, Python is needed, for plotting in `compare_results.py` script, additionally `matplotlib`

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y python3 python3-pip
pip3 install numpy matplotlib

# RHEL/CentOS
sudo yum install -y python3 python3-pip
pip3 install numpy matplotlib
```

### Setup SSH Key Authentication

On your control machine:
```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id user@server-vm
ssh-copy-id user@client1-vm
ssh-copy-id user@client2-vm
ssh-copy-id user@client3-vm
```

Test passwordless login:
```bash
ssh user@server-vm "hostname"
```

## Installation

1. **Download all scripts to your control machine:**
   - `server_measure.sh`
   - `client_measure.sh`
   - `orchestrator.sh`
   - `analyze_results.py`
   - `compare_results.py`

2. **Make scripts executable:**
```bash
chmod +x *.sh *.py
```

3. **Create configuration files** (see examples below)

## Configuration Files

### Example: `multicast_test.conf`

```yaml
server_vm: root@your-ip
client_vms:
  - root@your-ip
  - root@your-ip
  - root@your-ip
clients_per_vm: 2
iterations: 3
test_name: multicast_test
server_binary: /path/to/multicast
client_binary: /path/to/multicast
server_args: server 4433 4434 /path/to/cert /path/to/key 24000 /path/to/served-file.mp4 3
client_args: client SERVER_IP 4433 /path/to/client/folder 24000
```

### Example: `unicast_test.conf`

```yaml
server_vm: root@your-ip
client_vms:
  - root@your-ip
  - root@your-ip
  - root@your-ip
clients_per_vm: 1
iterations: 1
test_name: unicast_test
server_binary: /path/to/dgramspl
client_binary: /path/to/dgramspl
server_args: server 4433 /path/to/cert /path/to/key /path/to/served-file.mp4
client_args: client SERVER_IP 4433 /path/to/client/folder
```

**Note:** 
- `SERVER_IP` is automatically replaced with the actual server IP address.
- `clients_per_vm` specifies how many client processes to start on each VM (default: 1)
- `iterations` specifies how many times to run the test (default: 1). Results will be averaged.
- Total clients = number of client VMs × clients_per_vm

**See also:**
- [Usage of the multicast demo program](https://github.com/j0nem/picoquic-multicast/blob/multicast/multicast_sample/README.md)
- [Usage of the unicast demo program](https://github.com/j0nem/picoquic-multicast/blob/multicast/datagram_sample/README.md)

## Usage

### Option 1: Fully Automated Test (Recommended)

Run the entire distributed test from your control machine:

```bash
# Run multicast test (3 iterations)
./orchestrator.sh multicast_test.conf
# Will run 3 times automatically with 30s pause between iterations
# Press Ctrl+C during any iteration to stop

# Run unicast test (3 iterations)
./orchestrator.sh unicast_test.conf

# Compare results with averaging and plots
./compare_results.py "results/multicast_test_iter*" "results/unicast_test_iter*"
# This will:
# - Average results across all iterations
# - Calculate standard deviations
# - Generate comparison plots (CPU, memory, network)
# - Save plots to results/ directory
```

**The orchestrator will:**
1. Upload scripts to all VMs
2. Run the test multiple times (based on `iterations` config)
3. For each iteration:
   - Start the server
   - Start multiple clients on each client VM
   - Wait for you to press Ctrl+C (or for clients to finish naturally)
   - Stop all processes gracefully
   - Collect all results automatically
   - Generate analysis reports
4. Store results in separate iteration directories

### Option 2: Manual Per-VM Execution

If you prefer more control, run measurements manually on each VM:

**On Server VM:**
```bash
./server_measure.sh /path/to/binary test_name server 4433 4434 /path/to/cert /path/to/key 24000 /path/to/served-file.mp4 3
# Press Ctrl+C when done
```

**On Each Client VM (with multiple clients):**
```bash
./client_measure.sh /path/to/binary test_name 3 server_ip 4433 /path/to/client/folder
# This starts 3 client processes on this VM
# Press Ctrl+C to stop all clients on this VM
```

**Collect and Analyze:**
```bash
# Download results from server
scp -r user@server-vm:~/quic_tests/results/test_name_* ./local_results/

# Analyze
python3 analyze_results.py ./local_results/test_name_*
```

## Understanding the Results

### Directory Structure

After running tests, you'll have:

```
results/
├── multicast_test_iter1_20260116_143022/
│   ├── server/
│   │   ├── server_time.log          # Resource usage summary
│   │   ├── pidstat.log               # CPU/memory over time
│   │   ├── network_stats.log         # Interface statistics
│   │   ├── server_pid                # Server process ID
│   │   └── server_stdout.log         # Server output
│   ├── client_vm0/
│   │   ├── client_1/                 # First client on this VM
│   │   │   ├── stdout.log
│   │   │   └── time.log
│   │   ├── client_2/                 # Second client on this VM
│   │   │   ├── stdout.log
│   │   │   └── time.log
│   │   └── test_config.txt
│   ├── client_vm1/
│   │   └── ...
│   ├── server_analysis.txt
│   └── test_summary.txt
├── multicast_test_iter2_20260116_144530/
│   └── ...
├── multicast_test_iter3_20260116_150045/
│   └── ...
├── cpu_memory_comparison.png         # Generated plots
└── network_comparison.png
```

### Key Metrics

**CPU Usage:**
- Average CPU % - Overall CPU utilization
- Peak CPU % - Maximum CPU spike
- User Time - CPU time in user mode
- System Time - CPU time in kernel mode

**Memory Usage:**

Based on RSS (Resident Set Size) - Physical memory used

- Average Memory - Mean memory consumption
- Peak Memory - Maximum memory used

**Network:**
- Total Packets - Number of packets transmitted/received
- Data Transfer - Total bytes transferred
- Packet Rate - Packets per second
- Data Rate - Bytes per second

**Context Switches:**
- Voluntary - Process yielded CPU (I/O wait, etc.)
- Involuntary - Process preempted by scheduler

### Interpretation

When comparing multicast vs unicast:

- **Positive improvement %** = Multicast is better (uses fewer resources)
- **Negative improvement %** = Unicast is better

Expected multicast advantages:
- **Network traffic:** Should see significant reduction (50-75%) with multiple clients
- **CPU usage:** May be slightly higher due to multicast overhead
- **Memory:** Similar between both versions

## Tips and Best Practices

### 1. Synchronize VM Clocks

```bash
# On all VMs
sudo apt-get install -y ntp
sudo systemctl enable ntp
sudo systemctl start ntp
```

### 2. Disable CPU Frequency Scaling (for consistent results)

```bash
# On all VMs
sudo apt-get install -y cpufrequtils
sudo cpufreq-set -g performance
```

### 3. Run Multiple Iterations

```bash
for i in {1..5}; do
    echo "Running test iteration $i..."
    ./orchestrator.sh multicast_test.conf &
    ORCH_PID=$!
    
    # Let it run for 60 seconds
    sleep 60
    
    # Stop it with Ctrl+C (SIGINT)
    kill -INT $ORCH_PID
    wait $ORCH_PID
    
    sleep 30
done
```

### 4. Vary Number of Clients

Test with different client counts to see multicast scaling benefits by adjusting `clients_per_vm`:

**Example configurations:**
```yaml
# Small scale: 3 VMs × 1 client = 3 total clients
clients_per_vm: 1

# Medium scale: 3 VMs × 3 clients = 9 total clients  
clients_per_vm: 3

# Large scale: 3 VMs × 5 clients = 15 total clients
clients_per_vm: 5
```

Or vary the number of client VMs in your config file.

### 6. Document Test Conditions

Always record:
- VM specifications (CPU, RAM, network)
- Network topology
- Any background processes
- OS version and kernel
- QUIC implementation version

## Troubleshooting

### Server fails to start

Check the logs:
```bash
cat results/test_name_*/server/server_stdout.log
cat results/test_name_*/server/server_orchestrator.log
```

### Multicast routing issues

```bash
# On server, add multicast route
sudo route add -net 224.0.0.0 netmask 240.0.0.0 dev eth0

# Verify multicast group membership
netstat -g
```

## Advanced Usage

### Custom Analysis

You can extend `compare_results.py` to add custom metrics:

```python
def parse_custom_metric(filepath):
    # Your custom parsing logic
    pass
```

### Real-time Monitoring

Watch metrics during test:

```bash
# On server VM
watch -n 1 'ps aux | grep server_binary'

# Monitor network in real-time
iftop -i eth0
```

### Export Results to CSV

Modify `compare_results.py` to output CSV format for spreadsheet analysis.

## Example Test Workflow

```bash
# 1. Prepare configuration with iterations
nano multicast_test.conf  # Set iterations: 5
nano unicast_test.conf    # Set iterations: 5

# 2. Run multicast tests (5 iterations)
./orchestrator.sh multicast_test.conf
# Each iteration: wait ~2 minutes, then press Ctrl+C
# 30 seconds between iterations

# 3. Run unicast tests (5 iterations)
./orchestrator.sh unicast_test.conf
# Each iteration: wait ~2 minutes, then press Ctrl+C

# 4. Compare results with statistical analysis
./compare_results.py \
    "results/multicast_test_iter*" \
    "results/unicast_test_iter*" \
    | tee comparison_report.txt

# 5. View generated plots
xdg-open results/cpu_memory_comparison.png
xdg-open results/network_comparison.png

# 6. Examine individual iteration results if needed
cat results/multicast_test_iter1_*/server_analysis.txt
cat results/multicast_test_iter2_*/server_analysis.txt
```
