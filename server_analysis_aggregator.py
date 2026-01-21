#!/usr/bin/env python3
"""
Aggregate server analysis results across multiple test iterations.
Processes server_analysis.txt files from different test scenarios and iterations,
calculating average metrics for CPU, memory, and network usage.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List
import numpy as np
import matplotlib.pyplot as plt


@dataclass
class ServerMetrics:
    """Container for server performance metrics."""
    avg_cpu: float
    peak_cpu: float
    avg_memory_mib: float
    peak_memory_mib: float
    avg_packets_received: float
    peak_packets_received: float
    avg_packets_sent: float
    peak_packets_sent: float
    avg_kib_received: float
    peak_kib_received: float
    avg_kib_sent: float
    peak_kib_sent: float


def parse_server_analysis(file_path: Path) -> ServerMetrics:
    """Parse a server_analysis.txt file and extract metrics."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Extract CPU statistics
    avg_cpu = float(re.search(r'Average CPU Usage:\s+([\d.]+)%', content).group(1))
    peak_cpu = float(re.search(r'Peak CPU Usage:\s+([\d.]+)%', content).group(1))
    
    # Extract Memory statistics
    avg_mem = float(re.search(r'Average Memory:\s+([\d.]+)\s+MiB', content).group(1))
    peak_mem = float(re.search(r'Peak Memory:\s+([\d.]+)\s+MiB', content).group(1))
    
    # Extract Network statistics
    avg_pkt_recv = float(re.search(r'Average Packets Received:\s+([\d.]+)\s+packets/s', content).group(1))
    peak_pkt_recv = float(re.search(r'Peak Packets Received:\s+([\d.]+)\s+packets/s', content).group(1))
    avg_pkt_sent = float(re.search(r'Average Packets Sent:\s+([\d.]+)\s+packets/s', content).group(1))
    peak_pkt_sent = float(re.search(r'Peak Packets Sent:\s+([\d.]+)\s+packets/s', content).group(1))
    
    avg_kib_recv = float(re.search(r'Average KiB Received:\s+([\d.]+)\s+KiB/s', content).group(1))
    peak_kib_recv = float(re.search(r'Peak KiB Received:\s+([\d.]+)\s+KiB/s', content).group(1))
    avg_kib_sent = float(re.search(r'Average KiB Sent:\s+([\d.]+)\s+KiB/s', content).group(1))
    peak_kib_sent = float(re.search(r'Peak KiB Sent:\s+([\d.]+)\s+KiB/s', content).group(1))
    
    return ServerMetrics(
        avg_cpu=avg_cpu,
        peak_cpu=peak_cpu,
        avg_memory_mib=avg_mem,
        peak_memory_mib=peak_mem,
        avg_packets_received=avg_pkt_recv,
        peak_packets_received=peak_pkt_recv,
        avg_packets_sent=avg_pkt_sent,
        peak_packets_sent=peak_pkt_sent,
        avg_kib_received=avg_kib_recv,
        peak_kib_received=peak_kib_recv,
        avg_kib_sent=avg_kib_sent,
        peak_kib_sent=peak_kib_sent
    )


def extract_scenario_name(folder_name: str) -> str:
    """Extract scenario name from folder name (e.g., multicast_12_clients_iter1_... -> multicast_12_clients)."""
    match = re.match(r'(.+?)_iter\d+_', folder_name)
    scenario = match.group(1) if match else folder_name
    client_number = re.search(r'([^_]+)_(\d+)_', scenario).group(2)

    if (len(client_number) == 1):
        client_number = f"0{client_number}"

    first_part = match = re.match(r'([^_\d]+_)\d+(_[^_]+)', scenario).group(1)
    last_part = match = re.match(r'([^_\d]+_)\d+(_[^_]+)', scenario).group(2)
    scenario = f"{first_part}{client_number}{last_part}"

    return scenario


def calculate_averages(metrics_list: List[ServerMetrics]) -> ServerMetrics:
    """Calculate average metrics from a list of ServerMetrics."""
    n = len(metrics_list)
    return ServerMetrics(
        avg_cpu=sum(m.avg_cpu for m in metrics_list) / n,
        peak_cpu=sum(m.peak_cpu for m in metrics_list) / n,
        avg_memory_mib=sum(m.avg_memory_mib for m in metrics_list) / n,
        peak_memory_mib=sum(m.peak_memory_mib for m in metrics_list) / n,
        avg_packets_received=sum(m.avg_packets_received for m in metrics_list) / n,
        peak_packets_received=sum(m.peak_packets_received for m in metrics_list) / n,
        avg_packets_sent=sum(m.avg_packets_sent for m in metrics_list) / n,
        peak_packets_sent=sum(m.peak_packets_sent for m in metrics_list) / n,
        avg_kib_received=sum(m.avg_kib_received for m in metrics_list) / n,
        peak_kib_received=sum(m.peak_kib_received for m in metrics_list) / n,
        avg_kib_sent=sum(m.avg_kib_sent for m in metrics_list) / n,
        peak_kib_sent=sum(m.peak_kib_sent for m in metrics_list) / n
    )

def plot_metrics_over_clients(client_counts, unicast_values, multicast_values, title, axis_title, filename, output_dir='results'):
    """
    Plot resource usage comparison between unicast and multicast across different client counts.
    
    Parameters:
    -----------
    client_counts : list or array
        Number of clients for each measurement point (e.g., [10, 50, 100, 200, 500])
    unicast_values : list or array
        Usage percentages for unicast (e.g., [15, 35, 65, 85, 95])
    multicast_values : list or array
        Usage percentages for multicast (e.g., [10, 12, 15, 18, 20])
    title : str
        Title of the plot
    axis_title : str
        Axis title (unit of metric)
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Set up bar positions
    x = np.arange(len(client_counts))
    width = 0.35
    
    # Create bars
    ax.bar(x - width/2, unicast_values, width, label='Unicast', 
                   color='#e74c3c', alpha=0.8)
    ax.bar(x + width/2, multicast_values, width, label='Multicast', 
                   color='#3498db', alpha=0.8)
    
    # Create line showing client counts
    ax2 = ax.twinx()
    line = ax2.plot(x, client_counts, 'o-', color='#26844d', linewidth=2, 
                    markersize=8, label='Number of Clients')
    ax2.set_ylabel('Number of Clients', fontsize=12, color="#26844d")
    ax2.tick_params(axis='y', labelcolor='#26844d')
    
    # Labels and formatting
    # ax.set_xlabel('Test Configuration', fontsize=12)
    ax.set_ylabel(axis_title, fontsize=12)
    ax.set_title(title, 
                 fontsize=14, fontweight='bold')
    ax.set_xticks([])
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    ax.set_ylim(0, max(max(unicast_values), max(multicast_values)) * 1.13)
    ax2.set_ylim(0, max(client_counts) * 1.13)
    
    # Combine legends
    ax.legend(loc='upper left', fontsize=10)
    ax2.legend(loc='upper right', fontsize=10)
    
    plt.tight_layout()

    plt.savefig(os.path.join(output_dir, f'{filename}.png'), dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_dir}/{filename}.png")
    plt.close()

    return fig, ax, ax2


def main(base_dir: str = '.'):
    """Main function to process all server analysis files."""
    base_path = Path(base_dir)
    
    # Group metrics by scenario
    scenario_metrics: Dict[str, List[ServerMetrics]] = defaultdict(list)
    
    # Find all server_analysis.txt files
    for folder in base_path.iterdir():
        if not folder.is_dir():
            continue
        
        analysis_file = folder / 'server_analysis.txt'
        if not analysis_file.exists():
            continue
        
        scenario = extract_scenario_name(folder.name)
        
        try:
            metrics = parse_server_analysis(analysis_file)
            scenario_metrics[scenario].append(metrics)
        except Exception as e:
            print(f"Error processing {folder.name}: {e}")
    
    # Calculate and display averages
    print("\n" + "="*80)
    print("AGGREGATED RESULTS - AVERAGES ACROSS ITERATIONS")
    print("="*80 + "\n")

    multicast_avg_cpu = []
    unicast_avg_cpu = []

    multicast_avg_mem = []
    unicast_avg_mem = []

    multicast_avg_sent = []
    unicast_avg_sent = []

    number_of_clients = []

    for scenario in sorted(scenario_metrics.keys()):
        metrics_list = scenario_metrics[scenario]

        avg_metrics = calculate_averages(metrics_list)
        iterations = len(metrics_list)

        type = str(re.search(r'([^_]+)_(\d+)_', scenario).group(1))
        client_number = int(re.search(r'([^_]+)_(\d+)_', scenario).group(2))

        if client_number not in number_of_clients:
            number_of_clients.append(client_number)

        if type == 'unicast':
            unicast_avg_cpu.append(avg_metrics.avg_cpu)
            unicast_avg_mem.append(avg_metrics.avg_memory_mib)
            unicast_avg_sent.append(avg_metrics.avg_kib_sent)

        if type == 'multicast':
            multicast_avg_cpu.append(avg_metrics.avg_cpu)
            multicast_avg_mem.append(avg_metrics.avg_memory_mib)
            multicast_avg_sent.append(avg_metrics.avg_kib_sent)
        
        print(f"Scenario: {scenario}")
        print(f"Iterations: {iterations}")
        print("-" * 80)
        
        print("\nCPU Usage:")
        print(f"  Average CPU: {avg_metrics.avg_cpu:.2f}%")
        print(f"  Peak CPU:    {avg_metrics.peak_cpu:.2f}%")
        
        print("\nMemory Usage:")
        print(f"  Average Memory: {avg_metrics.avg_memory_mib:.2f} MiB")
        print(f"  Peak Memory:    {avg_metrics.peak_memory_mib:.2f} MiB")
        
        print("\nNetwork - Packets:")
        print(f"  Average Packets Received: {avg_metrics.avg_packets_received:.2f} packets/s")
        print(f"  Peak Packets Received:    {avg_metrics.peak_packets_received:.2f} packets/s")
        print(f"  Average Packets Sent:     {avg_metrics.avg_packets_sent:.2f} packets/s")
        print(f"  Peak Packets Sent:        {avg_metrics.peak_packets_sent:.2f} packets/s")
        
        print("\nNetwork - Throughput:")
        print(f"  Average KiB Received: {avg_metrics.avg_kib_received:.2f} KiB/s")
        print(f"  Peak KiB Received:    {avg_metrics.peak_kib_received:.2f} KiB/s")
        print(f"  Average KiB Sent:     {avg_metrics.avg_kib_sent:.2f} KiB/s")
        print(f"  Peak KiB Sent:        {avg_metrics.peak_kib_sent:.2f} KiB/s")
        
        print("\n" + "="*80 + "\n")

    plot_metrics_over_clients(number_of_clients, unicast_avg_cpu, multicast_avg_cpu, 
        'CPU Usage: Unicast vs Multicast across different client counts', 
        'Average CPU usage (%)', 'cpu_usage_across_clients')
    
    plot_metrics_over_clients(number_of_clients, unicast_avg_mem, multicast_avg_mem, 
        'Memory Usage: Unicast vs Multicast across different client counts', 
        'Average Memory usage (MiB)', 'memory_usage_across_clients')
    
    plot_metrics_over_clients(number_of_clients, unicast_avg_sent, multicast_avg_sent, 
        'Network Usage: Unicast vs Multicast across different client counts', 
        'Average sending throughput (KiB/s)', 'network_sent_across_clients')

if __name__ == '__main__':
    import sys
    
    # Use current directory if no argument provided
    directory = sys.argv[1] if len(sys.argv) > 1 else '.'
    main(directory)
