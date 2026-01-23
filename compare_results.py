#!/usr/bin/env python3
"""
compare_results.py - Compare multicast vs unicast QUIC performance with averaging and plotting
Usage: ./compare_results.py <multicast_results_pattern> <unicast_results_pattern>
Example: ./compare_results.py "results/multicast_test_iter*" "results/unicast_test_iter*"
         ./compare_results.py results/multicast_test_20260118_* results/unicast_test_20260118_*
"""

import sys
import os
import re
import json
import glob
import numpy as np
import matplotlib.pyplot as plt
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
            'user_time': r'User time \(seconds\): ([\d.]+)',
            'system_time': r'System time \(seconds\): ([\d.]+)',
            'cpu_percent': r'Percent of CPU this job got: (\d+)%',
            'max_memory_kb': r'Maximum resident set size \(kbytes\): (\d+)',
            'voluntary_switches': r'Voluntary context switches: (\d+)',
            'involuntary_switches': r'Involuntary context switches: (\d+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                stats[key] = float(match.group(1))
    
    return stats

def parse_pidstat_log(filepath):
    """Parse pidstat output with -t flag (threads) and proper column detection"""
    stats = {
        'cpu_values': [],
        'cpu_avg': 0.0,
        'cpu_peak': 0.0,
        'memory_values': [],
        'memory_avg': 0.0,
        'memory_peak': 0.0,
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
                            stats['cpu_values'].append(cpu)
                            
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
                            stats['memory_values'].append(rss)
                    except (ValueError, IndexError):
                        pass

                i += 1
        i += 1
    
    # Calculate statistics
    if stats['cpu_values']:
        stats['cpu_avg'] = sum(stats['cpu_values']) / len(stats['cpu_values'])
        stats['cpu_peak'] = max(stats['cpu_values'])
    
    if stats['memory_values']:
        stats['memory_avg'] = sum(stats['memory_values']) / len(stats['memory_values'])
        stats['memory_peak'] = max(stats['memory_values'])
    
    # Calculate per-thread averages
    for tid, data in stats['threads'].items():
        if data['cpu']:
            data['cpu_avg'] = sum(data['cpu']) / len(data['cpu'])
            data['cpu_peak'] = max(data['cpu'])
    
    return stats

def parse_network_log(filepath):
    """Parse sar network measures output with proper column detection"""
    stats = {
        'pkts_recv_values': [],
        'pkts_recv_avg': 0.0,
        'pkts_recv_peak': 0.0,
        'pkts_recv_total': 0,
        'pkts_sent_values': [],
        'pkts_sent_avg': 0.0,
        'pkts_sent_peak': 0.0,
        'pkts_sent_total': 0,
        'kib_recv_values': [],
        'kib_recv_avg': 0.0,
        'kib_recv_peak': 0.0,
        'kib_recv_total': 0.0,
        'kib_sent_values': [],
        'kib_sent_avg': 0.0,
        'kib_sent_peak': 0.0,
        'kib_sent_total': 0.0,
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
                        stats['pkts_recv_values'].append(float(parts[rxpck_index]))
                        stats['pkts_sent_values'].append(float(parts[txpck_index]))
                        stats['kib_recv_values'].append(float(parts[rxkb_index]))
                        stats['kib_sent_values'].append(float(parts[txkb_index]))
                    except (ValueError, IndexError) as e:
                        pass
                i += 1
        i += 1
    
    # Calculate statistics
    if stats['pkts_recv_values']:
        stats['pkts_recv_avg'] = sum(stats['pkts_recv_values']) / len(stats['pkts_recv_values'])
        stats['pkts_recv_peak'] = max(stats['pkts_recv_values'])
        stats['pkts_recv_total'] = sum(stats['pkts_recv_values'])

    if stats['pkts_sent_values']:
        stats['pkts_sent_avg'] = sum(stats['pkts_sent_values']) / len(stats['pkts_sent_values'])
        stats['pkts_sent_peak'] = max(stats['pkts_sent_values'])
        stats['pkts_sent_total'] = sum(stats['pkts_sent_values'])

        stats['pkts_total_avg'] = (sum(stats['pkts_sent_values']) + sum(stats['pkts_recv_values'])) / (len(stats['pkts_sent_values']) + len(stats['pkts_recv_values']))
        stats['pkts_total_peak'] = max(stats['pkts_sent_values'])

    if stats['kib_recv_values']:
        stats['kib_recv_avg'] = sum(stats['kib_recv_values']) / len(stats['kib_recv_values'])
        stats['kib_recv_peak'] = max(stats['kib_recv_values'])
        stats['kib_recv_total'] = sum(stats['kib_recv_values'])

    if stats['kib_sent_values']:
        stats['kib_sent_avg'] = sum(stats['kib_sent_values']) / len(stats['kib_sent_values'])
        stats['kib_sent_peak'] = max(stats['kib_sent_values'])
        stats['kib_sent_total'] = sum(stats['kib_sent_values'])

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
#             'total_packets': r'Number of packets:\s+(\d+)',
#             'file_size_bytes': r'File size:\s+(\d+)',
#             'data_size_bytes': r'Data size:\s+(\d+)',
#             'avg_packet_rate': r'Average packet rate:\s+([\d.]+)',
#             'avg_data_rate': r'Average data rate:\s+([\d.]+)',
#         }
        
#         for key, pattern in patterns.items():
#             match = re.search(pattern, output)
#             if match:
#                 stats[key] = float(match.group(1))
#     except:
#         stats['file_size_bytes'] = os.path.getsize(pcap_file) if os.path.exists(pcap_file) else 0
    
#     return stats

def load_results(results_dir):
    """Load all results from a test directory"""
    server_dir = os.path.join(results_dir, 'server')
    
    results = {
        'time_stats': parse_time_log(os.path.join(server_dir, 'server_time.log')),
        'pidstat': parse_pidstat_log(os.path.join(server_dir, 'pidstat.log')),
        'network': parse_network_log(os.path.join(server_dir, 'network_stats.log')),
    }
    
    return results

def load_multiple_results(pattern):
    """Load results from multiple test runs matching pattern"""
    dirs = sorted(glob.glob(pattern))
    if not dirs:
        return []
    
    all_results = []
    for dir_path in dirs:
        if os.path.isdir(dir_path):
            results = load_results(dir_path)
            all_results.append(results)
    
    return all_results

def aggregate_results(results_list):
    """Aggregate multiple test results into mean and std"""
    if not results_list:
        return None
    
    aggregated = {
        'time_stats': {},
        'pidstat': {},
        'network': {},
    }
    
    # Collect all metrics
    for category in ['time_stats', 'pidstat', 'network']:
        metrics = defaultdict(list)
        for result in results_list:
            for key, value in result[category].items():
                if (isinstance(value, float) or isinstance(value, int)) and value > 0:
                    metrics[key].append(value)

        # Calculate mean and std
        for key, values in metrics.items():
            if values:
                aggregated[category][key] = {
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'min': np.min(values),
                    'max': np.max(values),
                    'count': len(values)
                }
    
    return aggregated

def format_bytes(bytes_val):
    """Format bytes in human readable format"""
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def calculate_improvement(multicast_val, unicast_val):
    """Calculate percentage improvement"""
    if unicast_val == 0:
        return 0
    return ((unicast_val - multicast_val) / unicast_val) * 100

def print_comparison(multicast_agg, unicast_agg, multicast_count, unicast_count, title):
    """Print detailed comparison"""
    
    print("=" * 80)
    print(f"{title}: Multicast vs Unicast performance comparison")
    print("=" * 80)
    print()
    print(f"Multicast tests: {multicast_count}")
    print(f"Unicast tests: {unicast_count}")
    print()
    
    # CPU Usage
    print("=" * 80)
    print("CPU USAGE")
    print("=" * 80)
    
    m_cpu = multicast_agg['pidstat'].get('cpu_avg', {}).get('mean', 0)
    m_cpu_std = multicast_agg['pidstat'].get('cpu_avg', {}).get('std', 0)
    u_cpu = unicast_agg['pidstat'].get('cpu_avg', {}).get('mean', 0)
    u_cpu_std = unicast_agg['pidstat'].get('cpu_avg', {}).get('std', 0)
    cpu_improvement = calculate_improvement(m_cpu, u_cpu)
    
    print(f"{'Metric':<30} {'Multicast':<25} {'Unicast':<25} {'Improvement':<15}")
    print("-" * 95)
    print(f"{'Avg CPU %':<30} {f'{m_cpu:.2f} ± {m_cpu_std:.2f}':<25} {f'{u_cpu:.2f} ± {u_cpu_std:.2f}':<25} {cpu_improvement:>+.2f}%")
    
    m_cpu_peak = multicast_agg['pidstat'].get('cpu_peak', {}).get('mean', 0)
    u_cpu_peak = unicast_agg['pidstat'].get('cpu_peak', {}).get('mean', 0)
    cpu_peak_improvement = calculate_improvement(m_cpu_peak, u_cpu_peak)
    
    print(f"{'Peak CPU %':<30} {m_cpu_peak:<25.2f} {u_cpu_peak:<25.2f} {cpu_peak_improvement:>+.2f}%")
    print()
    
    # Memory
    print("=" * 80)
    print("MEMORY USAGE")
    print("=" * 80)
    
    m_mem = multicast_agg['pidstat'].get('memory_avg', {}).get('mean', 0)
    m_mem_std = multicast_agg['pidstat'].get('memory_avg', {}).get('std', 0)
    u_mem = unicast_agg['pidstat'].get('memory_avg', {}).get('mean', 0)
    u_mem_std = unicast_agg['pidstat'].get('memory_avg', {}).get('std', 0)
    mem_improvement = calculate_improvement(m_mem, u_mem)
    
    print(f"{'Metric':<30} {'Multicast':<25} {'Unicast':<25} {'Improvement':<15}")
    print("-" * 95)
    print(f"{'Avg Memory (KiB)':<30} {f'{m_mem:.0f} ± {m_mem_std:.0f}':<25} {f'{u_mem:.0f} ± {u_mem_std:.0f}':<25} {mem_improvement:>+.2f}%")
    print(f"{'Avg Memory':<30} {format_bytes(m_mem*1024):<25} {format_bytes(u_mem*1024):<25}")
    print()
    
    # Network
    print("=" * 80)
    print("NETWORK USAGE")
    print("=" * 80)
    
    m_packets_sent = multicast_agg['network'].get('pkts_sent_total', {}).get('mean', 0)
    u_packets_sent = unicast_agg['network'].get('pkts_sent_total', {}).get('mean', 0)
    packets_sent_improvement = calculate_improvement(m_packets_sent, u_packets_sent)

    m_packets_recv = multicast_agg['network'].get('pkts_recv_total', {}).get('mean', 0)
    u_packets_recv = unicast_agg['network'].get('pkts_recv_total', {}).get('mean', 0)
    packets_recv_improvement = calculate_improvement(m_packets_recv, u_packets_recv)
    
    m_data_sent = multicast_agg['network'].get('kib_sent_total', {}).get('mean', 0)
    u_data_sent = unicast_agg['network'].get('kib_sent_total', {}).get('mean', 0)
    data_sent_improvement = calculate_improvement(m_data_sent, u_data_sent)

    m_data_recv = multicast_agg['network'].get('kib_recv_total', {}).get('mean', 0)
    u_data_recv = unicast_agg['network'].get('kib_recv_total', {}).get('mean', 0)
    data_recv_improvement = calculate_improvement(m_data_recv, u_data_recv)
    
    print(f"{'Metric':<30} {'Multicast':<25} {'Unicast':<25} {'Improvement':<15}")
    print("-" * 95)
    print(f"{'Total Packets Sent':<30} {m_packets_sent:<25.0f} {u_packets_sent:<25.0f} {packets_sent_improvement:>+.2f}%")
    print(f"{'Total Packets Received':<30} {m_packets_recv:<25.0f} {u_packets_recv:<25.0f} {packets_recv_improvement:>+.2f}%")
    print(f"{'Total Data Sent':<30} {format_bytes(m_data_sent*1024):<25} {format_bytes(u_data_sent*1024):<25} {data_sent_improvement:>+.2f}%")
    print(f"{'Total Data Received':<30} {format_bytes(m_data_recv*1024):<25} {format_bytes(u_data_recv*1024):<25} {data_recv_improvement:>+.2f}%")
    print()
    
    return {
        'cpu': cpu_improvement,
        'memory': mem_improvement,
        'network_sent': data_sent_improvement,
        'network_received': data_recv_improvement
    }

def plot_comparison(multicast_agg, unicast_agg, title, output_dir='results'):
    """Create comparison plots"""
    
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
    except:
        pass
    
    os.makedirs(output_dir, exist_ok=True)
    
    # CPU Comparison
    fig, axs = plt.subplots(2, 2, figsize=(10, 10))
    
    metrics = ['cpu_avg', 'cpu_peak']
    labels = ['Average CPU %', 'Peak CPU %']
    
    m_vals = [multicast_agg['pidstat'].get(m, {}).get('mean', 0) for m in metrics]
    u_vals = [unicast_agg['pidstat'].get(m, {}).get('mean', 0) for m in metrics]
    m_errs = [multicast_agg['pidstat'].get(m, {}).get('std', 0) for m in metrics]
    u_errs = [unicast_agg['pidstat'].get(m, {}).get('std', 0) for m in metrics]
    
    x1 = np.arange(len(labels))
    width = 0.35
    
    ax1 = axs[0][0]
    ax1.bar(x1 - width/2, m_vals, width, yerr=m_errs, label='Multicast', alpha=0.8, capsize=5)
    ax1.bar(x1 + width/2, u_vals, width, yerr=u_errs, label='Unicast', alpha=0.8, capsize=5)
    ax1.set_ylabel('CPU Usage (%)')
    ax1.set_title('CPU Usage Comparison')
    ax1.set_xticks(x1)
    ax1.set_xticklabels(labels)
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # Memory Comparison
    mem_metrics = ['memory_avg', 'memory_peak']
    mem_labels = ['Average Memory', 'Peak Memory']
    
    m_mem_vals = [multicast_agg['pidstat'].get(m, {}).get('mean', 0)/1024 for m in mem_metrics]
    u_mem_vals = [unicast_agg['pidstat'].get(m, {}).get('mean', 0)/1024 for m in mem_metrics]
    m_mem_errs = [multicast_agg['pidstat'].get(m, {}).get('std', 0)/1024 for m in mem_metrics]
    u_mem_errs = [unicast_agg['pidstat'].get(m, {}).get('std', 0)/1024 for m in mem_metrics]
    
    x2 = np.arange(len(mem_labels))
    
    ax2 = axs[0][1]
    ax2.bar(x2 - width/2, m_mem_vals, width, yerr=m_mem_errs, label='Multicast', alpha=0.8, capsize=5)
    ax2.bar(x2 + width/2, u_mem_vals, width, yerr=u_mem_errs, label='Unicast', alpha=0.8, capsize=5)
    ax2.set_ylabel('Memory Usage (MiB)')
    ax2.set_title('Memory Usage Comparison')
    ax2.set_xticks(x2)
    ax2.set_xticklabels(mem_labels)
    ax2.legend()
    ax2.grid(axis='y', alpha=0.3)
    
    # Network Packets Comparison
    netpkt_metrics = ['pkts_sent_total', 'pkts_recv_total']
    netpkt_labels = ['Total Packets Sent', 'Total Packets Recieved']
    
    m_netp_vals = [multicast_agg['network'].get(m, {}).get('mean', 0) for m in netpkt_metrics]
    u_netp_vals = [unicast_agg['network'].get(m, {}).get('mean', 0) for m in netpkt_metrics]
    m_netp_errs = [multicast_agg['network'].get(m, {}).get('std', 0) for m in netpkt_metrics]
    u_netp_errs = [unicast_agg['network'].get(m, {}).get('std', 0) for m in netpkt_metrics]
    
    x3 = np.arange(len(netpkt_labels))
    
    ax3 = axs[1][0]
    ax3.bar(x3 - width/2, m_netp_vals, width, yerr=m_netp_errs, label='Multicast', alpha=0.8, capsize=5)
    ax3.bar(x3 + width/2, u_netp_vals, width, yerr=u_netp_errs, label='Unicast', alpha=0.8, capsize=5)
    ax3.set_ylabel('Number of Packets')
    ax3.set_title('Total Packets Comparison')
    ax3.set_xticks(x3)
    ax3.set_xticklabels(netpkt_labels)
    ax3.legend()
    ax3.grid(axis='y', alpha=0.3)
    
    # Network Data Comparison
    netdata_metrics = ['kib_sent_total', 'kib_recv_total']
    netdata_labels = ['Total data sent (MiB)', 'Total data received (MiB)']
    
    m_netd_vals = [multicast_agg['network'].get(m, {}).get('mean', 0)/1024 for m in netdata_metrics]
    u_netd_vals = [unicast_agg['network'].get(m, {}).get('mean', 0)/1024 for m in netdata_metrics]
    m_netd_errs = [multicast_agg['network'].get(m, {}).get('std', 0)/1024 for m in netdata_metrics]
    u_netd_errs = [unicast_agg['network'].get(m, {}).get('std', 0)/1024 for m in netdata_metrics]
    
    x4 = np.arange(len(netdata_labels))
    
    ax4 = axs[1][1]
    ax4.bar(x4 - width/2, m_netd_vals, width, yerr=m_netd_errs, label='Multicast', alpha=0.8, capsize=5)
    ax4.bar(x4 + width/2, u_netd_vals, width, yerr=u_netd_errs, label='Unicast', alpha=0.8, capsize=5)
    ax4.set_ylabel('Data Transfer (MiB)')
    ax4.set_title('Data Transfer Comparison')
    ax4.set_xticks(x4)
    ax4.set_xticklabels(netdata_labels)
    ax4.legend()
    ax4.grid(axis='y', alpha=0.3)

    fig.suptitle(title)

    file_name = str.lower(title).replace(' ','_')

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'{file_name}.svg'), dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_dir}/{file_name}.svg")
    plt.close()

def main():
    if len(sys.argv) < 4:
        print("Usage: ./compare_results.py <multicast_pattern> <unicast_pattern> <title>")
        print("Example: ./compare_results.py 'results/multicast_3_clients_iter*' 'results/unicast_3_clients_iter*' 'Performance with 3 clients'")
        sys.exit(1)
    
    multicast_pattern = sys.argv[1]
    unicast_pattern = sys.argv[2]
    title = sys.argv[3]
    
    print("Loading multicast results...")
    multicast_results = load_multiple_results(multicast_pattern)
    
    print("Loading unicast results...")
    unicast_results = load_multiple_results(unicast_pattern)
    
    if not multicast_results:
        print(f"Error: No multicast results found matching: {multicast_pattern}")
        sys.exit(1)
    
    if not unicast_results:
        print(f"Error: No unicast results found matching: {unicast_pattern}")
        sys.exit(1)
    
    print(f"Found {len(multicast_results)} multicast test(s) and {len(unicast_results)} unicast test(s)")
    print()
    
    # Aggregate results
    multicast_agg = aggregate_results(multicast_results)
    unicast_agg = aggregate_results(unicast_results)
    
    # Print comparison
    improvements = print_comparison(multicast_agg, unicast_agg, 
                                   len(multicast_results), len(unicast_results), title)
    
    # Generate plots
    print()
    print("Generating plots...")
    plot_comparison(multicast_agg, unicast_agg, title)
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("Positive improvement % means multicast performs better (uses less resources)")
    print("Negative improvement % means unicast performs better")
    print()
    
    for metric, improvement in improvements.items():
        status = "✓ Better" if improvement > 0 else "✗ Worse"
        print(f"{metric.upper():<20} {status:<15} ({improvement:>+.2f}%)")

if __name__ == '__main__':
    main()
