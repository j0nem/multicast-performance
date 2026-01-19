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
        
        if timestamp_match:
            # Check what type of section this is
            if 'UID' in line and '%CPU' in line:
                # This is a CPU stats header
                # Next line(s) contain the data
                i += 1
                while i < len(lines):
                    data_line = lines[i].strip()
                    
                    # Stop if we hit another timestamp or empty line
                    if re.match(r'\d{2}:\d{2}:\d{2}', data_line) or not data_line:
                        break
                    
                    # Skip lines that are just headers
                    if 'UID' in data_line or 'Linux' in data_line:
                        i += 1
                        continue
                    
                    # Parse the data line
                    parts = data_line.split()
                    if len(parts) >= 9:
                        try:
                            # Column positions (0-indexed):
                            # 0: timestamp, 1: UID, 2: TGID, 3: TID, 4: %usr, 5: %system, 
                            # 6: %guest, 7: %wait, 8: %CPU, 9: CPU, 10: Command
                            # But the timestamp might have AM/PM, so adjust
                            
                            # Find %CPU column - it's the one before CPU and after %wait
                            cpu_col = None
                            for idx, part in enumerate(parts):
                                if part == '%CPU' or (idx > 0 and parts[idx-1] in ['%wait', '%CPU']):
                                    # We're in the header, skip
                                    break
                                # Look for a numeric value that could be %CPU
                                # It should be after several other percentage values
                                if idx >= 7:  # After timestamp, UID, TGID, TID, %usr, %system, %guest, %wait
                                    try:
                                        cpu_val = float(part)
                                        # %CPU should be 0-100 (or slightly above with multiple threads)
                                        if 0 <= cpu_val <= 200:
                                            cpu_col = idx
                                            break
                                    except ValueError:
                                        continue
                            
                            # Fallback: assume standard position (column 8)
                            if cpu_col is None:
                                cpu_col = 8
                            
                            cpu = float(parts[cpu_col])
                            
                            # Sanity check: CPU should be reasonable
                            if 0 <= cpu <= 200:
                                stats['cpu']['values'].append(cpu)
                                
                                # Track per-thread stats if TGID/TID available
                                if len(parts) >= 4:
                                    tid = parts[3] if parts[3].isdigit() else parts[2]
                                    if tid not in stats['threads']:
                                        stats['threads'][tid] = {'cpu': [], 'name': parts[-1] if len(parts) > 10 else 'unknown'}
                                    stats['threads'][tid]['cpu'].append(cpu)
                        except (ValueError, IndexError) as e:
                            pass
                    
                    i += 1
                continue
                
            elif 'minflt/s' in line:
                # This is a memory stats header
                # Next line(s) contain the data
                i += 1
                while i < len(lines):
                    data_line = lines[i].strip()
                    
                    # Stop if we hit another timestamp or empty line
                    if re.match(r'\d{2}:\d{2}:\d{2}', data_line) or not data_line:
                        break
                    
                    # Skip headers
                    if 'UID' in data_line or 'minflt' in data_line or 'Linux' in data_line:
                        i += 1
                        continue
                    
                    # Parse the data line
                    parts = data_line.split()
                    # Format: timestamp [AM/PM] UID TGID TID minflt/s majflt/s VSZ RSS %MEM Command
                    if len(parts) >= 8:
                        try:
                            # RSS is typically column 7 (0-indexed)
                            # But need to account for AM/PM
                            rss_col = 7
                            if any(p in ['AM', 'PM'] for p in parts[:3]):
                                rss_col = 8
                            
                            # Find RSS - it's a large number in KB
                            rss = None
                            for idx in range(min(rss_col, len(parts)-1), len(parts)):
                                try:
                                    val = int(parts[idx])
                                    if val > 100:  # RSS should be reasonably large
                                        rss = val
                                        break
                                except ValueError:
                                    continue
                            
                            if rss is not None:
                                stats['memory']['values'].append(rss)
                        except (ValueError, IndexError):
                            pass
                    
                    i += 1
                continue
        
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

def parse_pcap_stats(results_dir):
    """Extract network statistics from packet capture"""
    stats = {}
    pcap_file = os.path.join(results_dir, 'network_capture.pcap')
    
    if not os.path.exists(pcap_file):
        return stats
    
    try:
        import subprocess
        output = subprocess.check_output(['capinfos', pcap_file], 
                                        stderr=subprocess.DEVNULL,
                                        universal_newlines=True)
        
        patterns = {
            'Number of packets': r'Number of packets:\s+(\d+)',
            'File size (bytes)': r'File size:\s+(\d+)',
            'Data size (bytes)': r'Data size:\s+(\d+)',
            'Average packet rate (packets/sec)': r'Average packet rate:\s+([\d.]+)',
            'Average data rate (bytes/sec)': r'Average data rate:\s+([\d.]+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                stats[key] = match.group(1)
    except:
        # Fallback: just get file size
        stats['File size (bytes)'] = str(os.path.getsize(pcap_file))
    
    return stats

def format_bytes(bytes_val):
    """Format bytes in human readable format"""
    try:
        bytes_val = float(bytes_val)
    except:
        return str(bytes_val)
    
    for unit in ['B', 'KB', 'MB', 'GB']:
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
            print(f"Average Memory (RSS): {pidstat_stats['memory']['avg']:.0f} KB")
            print(f"Average Memory: {format_bytes(pidstat_stats['memory']['avg'] * 1024)}")
            print(f"Peak Memory (RSS): {pidstat_stats['memory']['peak']:.0f} KB")
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
    print_section("Network Statistics")
    pcap_stats = parse_pcap_stats(results_dir)
    for key, value in pcap_stats.items():
        if 'bytes' in key.lower():
            print(f"{key}: {value} ({format_bytes(value)})")
        else:
            print(f"{key}: {value}")
    
    print()
    print("=" * 80)
    print("End of Analysis")
    print("=" * 80)

if __name__ == '__main__':
    main()
