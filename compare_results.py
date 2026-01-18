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
    """Parse pidstat output for averages and peaks"""
    stats = {'avg_cpu': 0, 'avg_memory': 0, 'peak_cpu': 0, 'peak_memory': 0}
    if not os.path.exists(filepath):
        return stats
    
    cpu_values = []
    mem_values = []
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for timestamp pattern followed by data
            if re.match(r'\d{2}:\d{2}:\d{2}', line):
                # Check what type of data follows
                if '%usr' in line or '%CPU' in line:
                    # Next line has CPU data
                    i += 1
                    if i < len(lines):
                        parts = lines[i].split()
                        if len(parts) >= 8 and parts[7].replace('.', '').isdigit():
                            try:
                                cpu = float(parts[7])
                                if cpu <= 100:  # Sanity check
                                    cpu_values.append(cpu)
                            except ValueError:
                                pass
                elif 'minflt/s' in line:
                    # Next line has memory data
                    i += 1
                    if i < len(lines):
                        parts = lines[i].split()
                        if len(parts) >= 6 and parts[5].isdigit():
                            try:
                                mem = float(parts[5])
                                mem_values.append(mem)
                            except ValueError:
                                pass
            i += 1
    
    if cpu_values:
        stats['avg_cpu'] = np.mean(cpu_values)
        stats['peak_cpu'] = np.max(cpu_values)
    
    if mem_values:
        stats['avg_memory'] = np.mean(mem_values)
        stats['peak_memory'] = np.max(mem_values)
    
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
            'total_packets': r'Number of packets:\s+(\d+)',
            'file_size_bytes': r'File size:\s+(\d+)',
            'data_size_bytes': r'Data size:\s+(\d+)',
            'avg_packet_rate': r'Average packet rate:\s+([\d.]+)',
            'avg_data_rate': r'Average data rate:\s+([\d.]+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, output)
            if match:
                stats[key] = float(match.group(1))
    except:
        stats['file_size_bytes'] = os.path.getsize(pcap_file) if os.path.exists(pcap_file) else 0
    
    return stats

def load_results(results_dir):
    """Load all results from a test directory"""
    server_dir = os.path.join(results_dir, 'server')
    
    results = {
        'time_stats': parse_time_log(os.path.join(server_dir, 'server_time.log')),
        'pidstat': parse_pidstat_log(os.path.join(server_dir, 'pidstat.log')),
        'network': parse_pcap_stats(server_dir),
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
                if value > 0:  # Only include valid values
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
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def calculate_improvement(multicast_val, unicast_val):
    """Calculate percentage improvement"""
    if unicast_val == 0:
        return 0
    return ((unicast_val - multicast_val) / unicast_val) * 100

def print_comparison(multicast_agg, unicast_agg, multicast_count, unicast_count):
    """Print detailed comparison"""
    
    print("=" * 80)
    print("MULTICAST vs UNICAST QUIC PERFORMANCE COMPARISON")
    print("=" * 80)
    print()
    print(f"Multicast tests: {multicast_count}")
    print(f"Unicast tests: {unicast_count}")
    print()
    
    # CPU Usage
    print("=" * 80)
    print("CPU USAGE")
    print("=" * 80)
    
    m_cpu = multicast_agg['pidstat'].get('avg_cpu', {}).get('mean', 0)
    m_cpu_std = multicast_agg['pidstat'].get('avg_cpu', {}).get('std', 0)
    u_cpu = unicast_agg['pidstat'].get('avg_cpu', {}).get('mean', 0)
    u_cpu_std = unicast_agg['pidstat'].get('avg_cpu', {}).get('std', 0)
    cpu_improvement = calculate_improvement(m_cpu, u_cpu)
    
    print(f"{'Metric':<30} {'Multicast':<25} {'Unicast':<25} {'Improvement':<15}")
    print("-" * 95)
    print(f"{'Avg CPU %':<30} {f'{m_cpu:.2f} ± {m_cpu_std:.2f}':<25} {f'{u_cpu:.2f} ± {u_cpu_std:.2f}':<25} {cpu_improvement:>+.2f}%")
    
    m_cpu_peak = multicast_agg['pidstat'].get('peak_cpu', {}).get('mean', 0)
    u_cpu_peak = unicast_agg['pidstat'].get('peak_cpu', {}).get('mean', 0)
    cpu_peak_improvement = calculate_improvement(m_cpu_peak, u_cpu_peak)
    
    print(f"{'Peak CPU %':<30} {m_cpu_peak:<25.2f} {u_cpu_peak:<25.2f} {cpu_peak_improvement:>+.2f}%")
    print()
    
    # Memory
    print("=" * 80)
    print("MEMORY USAGE")
    print("=" * 80)
    
    m_mem = multicast_agg['pidstat'].get('avg_memory', {}).get('mean', 0)
    m_mem_std = multicast_agg['pidstat'].get('avg_memory', {}).get('std', 0)
    u_mem = unicast_agg['pidstat'].get('avg_memory', {}).get('mean', 0)
    u_mem_std = unicast_agg['pidstat'].get('avg_memory', {}).get('std', 0)
    mem_improvement = calculate_improvement(m_mem, u_mem)
    
    print(f"{'Metric':<30} {'Multicast':<25} {'Unicast':<25} {'Improvement':<15}")
    print("-" * 95)
    print(f"{'Avg Memory (KB)':<30} {f'{m_mem:.0f} ± {m_mem_std:.0f}':<25} {f'{u_mem:.0f} ± {u_mem_std:.0f}':<25} {mem_improvement:>+.2f}%")
    print(f"{'Avg Memory':<30} {format_bytes(m_mem*1024):<25} {format_bytes(u_mem*1024):<25}")
    print()
    
    # Network
    print("=" * 80)
    print("NETWORK USAGE")
    print("=" * 80)
    
    m_packets = multicast_agg['network'].get('total_packets', {}).get('mean', 0)
    u_packets = unicast_agg['network'].get('total_packets', {}).get('mean', 0)
    packets_improvement = calculate_improvement(m_packets, u_packets)
    
    m_data = multicast_agg['network'].get('data_size_bytes', {}).get('mean', 0)
    u_data = unicast_agg['network'].get('data_size_bytes', {}).get('mean', 0)
    data_improvement = calculate_improvement(m_data, u_data)
    
    print(f"{'Metric':<30} {'Multicast':<25} {'Unicast':<25} {'Improvement':<15}")
    print("-" * 95)
    print(f"{'Total Packets':<30} {m_packets:<25.0f} {u_packets:<25.0f} {packets_improvement:>+.2f}%")
    print(f"{'Total Data':<30} {format_bytes(m_data):<25} {format_bytes(u_data):<25} {data_improvement:>+.2f}%")
    print()
    
    return {
        'cpu': cpu_improvement,
        'memory': mem_improvement,
        'network': data_improvement
    }

def plot_comparison(multicast_agg, unicast_agg, output_dir='results'):
    """Create comparison plots"""
    
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
    except:
        pass
    
    os.makedirs(output_dir, exist_ok=True)
    
    # CPU Comparison
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    metrics = ['avg_cpu', 'peak_cpu']
    labels = ['Average CPU %', 'Peak CPU %']
    
    m_vals = [multicast_agg['pidstat'].get(m, {}).get('mean', 0) for m in metrics]
    u_vals = [unicast_agg['pidstat'].get(m, {}).get('mean', 0) for m in metrics]
    m_errs = [multicast_agg['pidstat'].get(m, {}).get('std', 0) for m in metrics]
    u_errs = [unicast_agg['pidstat'].get(m, {}).get('std', 0) for m in metrics]
    
    x = np.arange(len(labels))
    width = 0.35
    
    ax1.bar(x - width/2, m_vals, width, yerr=m_errs, label='Multicast', alpha=0.8, capsize=5)
    ax1.bar(x + width/2, u_vals, width, yerr=u_errs, label='Unicast', alpha=0.8, capsize=5)
    ax1.set_ylabel('CPU Usage (%)')
    ax1.set_title('CPU Usage Comparison')
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # Memory Comparison
    mem_metrics = ['avg_memory', 'peak_memory']
    mem_labels = ['Average Memory', 'Peak Memory']
    
    m_mem_vals = [multicast_agg['pidstat'].get(m, {}).get('mean', 0)/1024 for m in mem_metrics]
    u_mem_vals = [unicast_agg['pidstat'].get(m, {}).get('mean', 0)/1024 for m in mem_metrics]
    m_mem_errs = [multicast_agg['pidstat'].get(m, {}).get('std', 0)/1024 for m in mem_metrics]
    u_mem_errs = [unicast_agg['pidstat'].get(m, {}).get('std', 0)/1024 for m in mem_metrics]
    
    x = np.arange(len(mem_labels))
    
    ax2.bar(x - width/2, m_mem_vals, width, yerr=m_mem_errs, label='Multicast', alpha=0.8, capsize=5)
    ax2.bar(x + width/2, u_mem_vals, width, yerr=u_mem_errs, label='Unicast', alpha=0.8, capsize=5)
    ax2.set_ylabel('Memory Usage (MB)')
    ax2.set_title('Memory Usage Comparison')
    ax2.set_xticks(x)
    ax2.set_xticklabels(mem_labels)
    ax2.legend()
    ax2.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'cpu_memory_comparison.png'), dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_dir}/cpu_memory_comparison.png")
    plt.close()
    
    # Network Comparison
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    
    net_metrics = ['total_packets', 'data_size_bytes']
    net_labels = ['Total Packets', 'Data Transfer (MB)']
    
    m_net_vals = [
        multicast_agg['network'].get('total_packets', {}).get('mean', 0),
        multicast_agg['network'].get('data_size_bytes', {}).get('mean', 0)/(1024*1024)
    ]
    u_net_vals = [
        unicast_agg['network'].get('total_packets', {}).get('mean', 0),
        unicast_agg['network'].get('data_size_bytes', {}).get('mean', 0)/(1024*1024)
    ]
    
    m_net_errs = [
        multicast_agg['network'].get('total_packets', {}).get('std', 0),
        multicast_agg['network'].get('data_size_bytes', {}).get('std', 0)/(1024*1024)
    ]
    u_net_errs = [
        unicast_agg['network'].get('total_packets', {}).get('std', 0),
        unicast_agg['network'].get('data_size_bytes', {}).get('std', 0)/(1024*1024)
    ]
    
    # Normalize for visualization (different scales)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    # Packets
    x = [0]
    width = 0.35
    ax1.bar(x[0] - width/2, [m_net_vals[0]], width, yerr=[m_net_errs[0]], 
            label='Multicast', alpha=0.8, capsize=5)
    ax1.bar(x[0] + width/2, [u_net_vals[0]], width, yerr=[u_net_errs[0]], 
            label='Unicast', alpha=0.8, capsize=5)
    ax1.set_ylabel('Number of Packets')
    ax1.set_title('Total Packets Comparison')
    ax1.set_xticks([0])
    ax1.set_xticklabels(['Packets'])
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # Data
    ax2.bar(x[0] - width/2, [m_net_vals[1]], width, yerr=[m_net_errs[1]], 
            label='Multicast', alpha=0.8, capsize=5)
    ax2.bar(x[0] + width/2, [u_net_vals[1]], width, yerr=[u_net_errs[1]], 
            label='Unicast', alpha=0.8, capsize=5)
    ax2.set_ylabel('Data Transfer (MB)')
    ax2.set_title('Data Transfer Comparison')
    ax2.set_xticks([0])
    ax2.set_xticklabels(['Data'])
    ax2.legend()
    ax2.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'network_comparison.png'), dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_dir}/network_comparison.png")
    plt.close()

def main():
    if len(sys.argv) < 3:
        print("Usage: ./compare_results.py <multicast_pattern> <unicast_pattern>")
        print("Example: ./compare_results.py 'results/multicast_test_iter*' 'results/unicast_test_iter*'")
        sys.exit(1)
    
    multicast_pattern = sys.argv[1]
    unicast_pattern = sys.argv[2]
    
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
                                   len(multicast_results), len(unicast_results))
    
    # Generate plots
    print()
    print("Generating plots...")
    plot_comparison(multicast_agg, unicast_agg)
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
