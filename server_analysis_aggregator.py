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
    return match.group(1) if match else folder_name


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
            print(f"Processed: {folder.name} -> {scenario}")
        except Exception as e:
            print(f"Error processing {folder.name}: {e}")
    
    # Calculate and display averages
    print("\n" + "="*80)
    print("AGGREGATED RESULTS - AVERAGES ACROSS ITERATIONS")
    print("="*80 + "\n")
    
    for scenario in sorted(scenario_metrics.keys()):
        metrics_list = scenario_metrics[scenario]
        avg_metrics = calculate_averages(metrics_list)
        iterations = len(metrics_list)
        
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


if __name__ == '__main__':
    import sys
    
    # Use current directory if no argument provided
    directory = sys.argv[1] if len(sys.argv) > 1 else '.'
    main(directory)
