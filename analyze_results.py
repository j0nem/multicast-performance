#!/usr/bin/env python3
"""
analyze_results.py - Analyze QUIC performance test results
Usage: ./analyze_results.py <results_directory>
"""

import sys
import os
import re
from pathlib import Path
from collections import defaultdict

def parse_time_log(filepath):
    """Parse /usr/bin/time output"""
    stats = {}
    if not os.path.exists(filepath):
        return stats
    
    with open(filepath, 'r') as f:
        content = f.read()
        
        patterns = {
            'User time (seconds)': r'User time \(seconds\): ([\d.]+)',
            'System time (seconds)': r'System time \(seconds\): ([\d.]+)',
            'Percent of CPU': r'Percent of CPU this job got: (\d+)%',
            'Maximum resident set size (kbytes)': r'Maximum resident set size \(kbytes\): (\d+)',
            'Voluntary context switches': r'Voluntary context switches: (\d+)',
            'Involuntary context switches': r'Involuntary context switches: (\d+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                stats[key] = match.group(1)
    
    return stats

def parse_pidstat_log(filepath):
    """Parse pidstat output with -t flag (threads) and proper column detection"""
    stats = {
        'cpu': {'avg': 0, 'peak': 0, 'values': []},
        'memory': {'avg': 0, 'peak': 0, 'values': []},
        'threads': {}
    }
    
    if not os.path.exists(filepath):
        return stats
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for timestamp pattern (handles both AM/PM and 24-hour format)
        # Pattern: HH:MM:SS AM/PM or HH:MM:SS
        timestamp_match = re.match(r'(\d{2}:\d{2}:\d{2})\s*(AM|PM)?', line)
        if timestamp_match and 'UID' in line and '%CPU' in line:
            # This is a CPU stats header
            # Next line(s) contain the data
            header_split = line.split()
            cpu_index = 9
            tid_index = 4
            for j in range(len(header_split)):
                if header_split[j] == '%CPU':
                    cpu_index = j
                if header_split[j] == 'TID': 
                    tid_index = j
            
            # Next line should be data line
            i += 1
            while i < len(lines):
                data_line = lines[i].strip()
                
                # Stop if we hit header or empty line
                if not data_line or 'UID' in data_line or 'Linux' in data_line:
                    break
                
                # Parse the data line
                parts = data_line.split()
                if len(parts) >= 9:
                    try:                        
                        cpu = float(parts[cpu_index])
                        
                        # Sanity check: CPU should be reasonable
                        if 0 <= cpu <= 200:
                            stats['cpu']['values'].append(cpu)
                            
                            # Track per-thread stats if TGID/TID available
                            if len(parts) >= 4:
                                tid = parts[tid_index]
                                if tid != '-':
                                    if tid not in stats['threads']:
                                        stats['threads'][tid] = {'cpu': [], 'name': parts[-1] if len(parts) > 9 else 'unknown'}
                                    stats['threads'][tid]['cpu'].append(cpu)
                    except (ValueError, IndexError) as e:
                        pass
                i += 1
                
        elif 'minflt/s' in line:
            # This is a memory stats header
            # Next line(s) contain the data
            header_split = line.split()
            rss_index = 8
            for j in range(len(header_split)):
                if header_split[j] == 'RSS':
                    rss_index = j
                    break

            # Next line should be data line
            i += 1
            while i < len(lines):
                data_line = lines[i].strip()
                
                # Stop if we hit empty line
                if not data_line or 'minflt' in data_line or 'Linux' in data_line:
                    break

                # Parse the data line
                parts = data_line.split()
                # Format: timestamp [AM/PM] UID TGID TID minflt/s majflt/s VSZ RSS %MEM Command
                if len(parts) >= 8:
                    try:
                        # Find RSS - it's a large number in KB
                        rss = None
                        try:
                            val = int(parts[rss_index])
                            if val > 100:  # RSS should be reasonably large
                                rss = val
                        except ValueError:
                            continue

                        if rss is not None:
                            stats['memory']['values'].append(rss)
                    except (ValueError, IndexError):
                        pass

                i += 1
        i += 1
    
    # Calculate statistics
    if stats['cpu']['values']:
        stats['cpu']['avg'] = sum(stats['cpu']['values']) / len(stats['cpu']['values'])
        stats['cpu']['peak'] = max(stats['cpu']['values'])
    
    if stats['memory']['values']:
        stats['memory']['avg'] = sum(stats['memory']['values']) / len(stats['memory']['values'])
        stats['memory']['peak'] = max(stats['memory']['values'])
    
    # Calculate per-thread averages
    for tid, data in stats['threads'].items():
        if data['cpu']:
            data['cpu_avg'] = sum(data['cpu']) / len(data['cpu'])
            data['cpu_peak'] = max(data['cpu'])
    
    return stats

def parse_network_log(filepath):
    """Parse sar network measures output with proper column detection"""
    stats = {
        'pkts_recv': {'avg': 0, 'peak': 0, 'total': 0, 'values': []},
        'pkts_sent': {'avg': 0, 'peak': 0, 'total': 0, 'values': []},
        'kib_recv': {'avg': 0, 'peak': 0, 'total': 0.0, 'values': []},
        'kib_sent': {'avg': 0, 'peak': 0, 'total': 0.0, 'values': []},
    }
    
    if not os.path.exists(filepath):
        return stats
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for timestamp pattern (handles both AM/PM and 24-hour format)
        # Pattern: HH:MM:SS AM/PM or HH:MM:SS
        timestamp_match = re.match(r'(\d{2}:\d{2}:\d{2})\s*(AM|PM)?', line)
        if timestamp_match and 'IFACE' in line:
            # This is a network stats header
            # Next line(s) contain the data
            header_split = line.split()
            if_index = 2
            rxpck_index = 3
            txpck_index = 4
            rxkb_index = 5
            txkb_index = 6
            for j in range(len(header_split)):
                if header_split[j] == 'IFACE':
                    if_index = j
                if header_split[j] == 'rxpck/s':
                    rxpck_index = j
                if header_split[j] == 'txpck/s': 
                    txpck_index = j
                if header_split[j] == 'rxkB/s': 
                    rxkb_index = j
                if header_split[j] == 'txkB/s': 
                    txkb_index = j
            
            # Next line should be data line
            i += 1
            while i < len(lines):
                data_line = lines[i].strip()
                
                # Stop if we hit header or empty line
                if not data_line or 'IFACE' in data_line or 'Linux' in data_line:
                    break

                # Do not analyze local interface
                if data_line[if_index] == 'lo':
                    i += 1
                    continue
                
                # Parse the data line
                parts = data_line.split()
                if len(parts) >= 7:
                    try:
                        stats['pkts_recv']['values'].append(float(parts[rxpck_index]))
                        stats['pkts_sent']['values'].append(float(parts[txpck_index]))
                        stats['kib_recv']['values'].append(float(parts[rxkb_index]))
                        stats['kib_sent']['values'].append(float(parts[txkb_index]))
                    except (ValueError, IndexError) as e:
                        pass
                i += 1
        i += 1
    
    # Calculate statistics
    if stats['pkts_recv']['values']:
        stats['pkts_recv']['avg'] = sum(stats['pkts_recv']['values']) / len(stats['pkts_recv']['values'])
        stats['pkts_recv']['peak'] = max(stats['pkts_recv']['values'])
        stats['pkts_recv']['total'] = sum(stats['pkts_recv']['values'])

    if stats['pkts_sent']['values']:
        stats['pkts_sent']['avg'] = sum(stats['pkts_sent']['values']) / len(stats['pkts_sent']['values'])
        stats['pkts_sent']['peak'] = max(stats['pkts_sent']['values'])
        stats['pkts_sent']['total'] = sum(stats['pkts_sent']['values'])

    if stats['kib_recv']['values']:
        stats['kib_recv']['avg'] = sum(stats['kib_recv']['values']) / len(stats['kib_recv']['values'])
        stats['kib_recv']['peak'] = max(stats['kib_recv']['values'])
        stats['kib_recv']['total'] = sum(stats['kib_recv']['values'])

    if stats['kib_sent']['values']:
        stats['kib_sent']['avg'] = sum(stats['kib_sent']['values']) / len(stats['kib_sent']['values'])
        stats['kib_sent']['peak'] = max(stats['kib_sent']['values'])
        stats['kib_sent']['total'] = sum(stats['kib_sent']['values'])

    return stats

# def parse_pcap_stats(results_dir):
#     """Extract network statistics from packet capture"""
#     stats = {}
#     pcap_file = os.path.join(results_dir, 'network_capture.pcap')
    
#     if not os.path.exists(pcap_file):
#         return stats
    
#     try:
#         import subprocess
#         output = subprocess.check_output(['capinfos', pcap_file], 
#                                         stderr=subprocess.DEVNULL,
#                                         universal_newlines=True)
        
#         patterns = {
#             'Number of packets': r'Number of packets:\s+(\d+)',
#             'File size (bytes)': r'File size:\s+(\d+)',
#             'Data size (bytes)': r'Data size:\s+(\d+)',
#             'Average packet rate (packets/sec)': r'Average packet rate:\s+([\d.]+)',
#             'Average data rate (bytes/sec)': r'Average data rate:\s+([\d.]+)',
#         }
        
#         for key, pattern in patterns.items():
#             match = re.search(pattern, output)
#             if match:
#                 stats[key] = match.group(1)
#     except:
#         # Fallback: just get file size
#         stats['File size (bytes)'] = str(os.path.getsize(pcap_file))
    
#     return stats

def format_bytes(bytes_val):
    """Format bytes in human readable format"""
    try:
        bytes_val = float(bytes_val)
    except:
        return str(bytes_val)
    
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def print_section(title):
    """Print a section header"""
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)
    print()

def main():
    if len(sys.argv) < 2:
        print("Usage: ./analyze_results.py <results_directory>")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    
    if not os.path.isdir(results_dir):
        print(f"Error: Directory {results_dir} not found")
        sys.exit(1)
    
    print("=" * 80)
    print("QUIC Performance Test Results Analysis")
    print("=" * 80)
    print()
    
    # Test configuration
    config_file = os.path.join(results_dir, 'test_config.txt')
    if os.path.exists(config_file):
        print_section("Test Configuration")
        with open(config_file, 'r') as f:
            print(f.read())
    
    # Server resource usage from /usr/bin/time
    time_file = os.path.join(results_dir, 'server_time.log')
    if os.path.exists(time_file):
        print_section("Server Resource Usage Summary")
        time_stats = parse_time_log(time_file)
        for key, value in time_stats.items():
            print(f"{key}: {value}")
    
    # CPU and Memory usage from pidstat
    pidstat_file = os.path.join(results_dir, 'pidstat.log')
    if os.path.exists(pidstat_file):
        print_section("CPU and Memory Statistics (pidstat)")
        pidstat_stats = parse_pidstat_log(pidstat_file)
        
        if pidstat_stats['cpu']['avg'] > 0:
            print(f"Average CPU Usage: {pidstat_stats['cpu']['avg']:.2f}%")
            print(f"Peak CPU Usage: {pidstat_stats['cpu']['peak']:.2f}%")
            print()
        
        if pidstat_stats['memory']['avg'] > 0:
            print(f"Average Memory (RSS): {pidstat_stats['memory']['avg']:.0f} KiB")
            print(f"Average Memory: {format_bytes(pidstat_stats['memory']['avg'] * 1024)}")
            print(f"Peak Memory (RSS): {pidstat_stats['memory']['peak']:.0f} KiB")
            print(f"Peak Memory: {format_bytes(pidstat_stats['memory']['peak'] * 1024)}")
            print()
        
        # Show per-thread statistics if available
        if pidstat_stats['threads']:
            print("Per-Thread CPU Statistics:")
            print(f"{'Thread ID':<15} {'Name':<20} {'Avg CPU %':<12} {'Peak CPU %':<12}")
            print("-" * 60)
            for tid, data in sorted(pidstat_stats['threads'].items()):
                if 'cpu_avg' in data:
                    print(f"{tid:<15} {data.get('name', 'unknown'):<20} {data['cpu_avg']:<12.2f} {data['cpu_peak']:<12.2f}")
            print()
    
        # Network statistics
    network_stats_file = os.path.join(results_dir, 'network_stats.log')
    if os.path.exists(network_stats_file):
        print_section("Network Statistics")
        network_stats = parse_network_log(network_stats_file)
        
        if network_stats['pkts_recv']['avg'] > 0:
            print(f"Average Packets Received: {network_stats['pkts_recv']['avg']:.2f} packets/s")
            print(f"Peak Packets Received: {network_stats['pkts_recv']['peak']:.2f} packets/s")
            print(f"Total Packets Received: {network_stats['pkts_recv']['total']} packets")
            print()

        if network_stats['pkts_sent']['avg'] > 0:
            print(f"Average Packets Sent: {network_stats['pkts_sent']['avg']:.2f} packets/s")
            print(f"Peak Packets Sent: {network_stats['pkts_sent']['peak']:.2f} packets/s")
            print(f"Total Packets Sent: {network_stats['pkts_sent']['total']} packets")
            print()
        
        if network_stats['kib_recv']['avg'] > 0:
            print(f"Average KiB Received: {network_stats['kib_recv']['avg']:.2f} KiB/s")
            print(f"Peak KiB Received: {network_stats['kib_recv']['peak']:.2f} KiB/s")
            print(f"Total KiB Received: {network_stats['kib_recv']['total']:.2f} KiB")
            print()

        if network_stats['kib_sent']['avg'] > 0:
            print(f"Average KiB Sent: {network_stats['kib_sent']['avg']:.2f} KiB/s")
            print(f"Peak KiB Sent: {network_stats['kib_sent']['peak']:.2f} KiB/s")
            print(f"Total KiB Sent: {network_stats['kib_sent']['total']:.2f} KiB")
            print()
    
    print()
    print("=" * 80)
    print("End of Analysis")
    print("=" * 80)

if __name__ == '__main__':
    main()
