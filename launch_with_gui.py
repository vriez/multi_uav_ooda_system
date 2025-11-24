#!/usr/bin/env python3
"""
Complete system launcher with GUI dashboard
"""
import subprocess
import time
import sys
import os
import threading

def launch_dashboard():
    """Launch web dashboard"""
    print("Starting Dashboard on http://localhost:8085")
    return subprocess.Popen(
        [sys.executable, '-m', 'visualization.web_dashboard'],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

def launch_gcs():
    """Launch GCS"""
    print("Starting GCS...")
    return subprocess.Popen(
        [sys.executable, '-m', 'gcs.main'],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

def launch_uav(uav_id, x, y, z=10):
    """Launch UAV"""
    print(f"Starting UAV {uav_id} at ({x}, {y}, {z})")
    return subprocess.Popen(
        [sys.executable, '-m', 'uav.client', str(uav_id), str(x), str(y), str(z)],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

def main():
    processes = []
    
    try:
        # Start dashboard first
        dashboard = launch_dashboard()
        processes.append(dashboard)
        time.sleep(2)
        
        # Start GCS
        gcs = launch_gcs()
        processes.append(gcs)
        time.sleep(2)
        
        # Start UAV fleet
        positions = [(0, 0, 10), (20, 0, 10), (40, 0, 10), (0, 20, 10), (20, 20, 10)]
        
        for i, (x, y, z) in enumerate(positions, start=1):
            uav = launch_uav(i, x, y, z)
            processes.append(uav)
            time.sleep(0.5)
        
        print(f"\n{'='*60}")
        print(f"System running!")
        print(f"Dashboard: http://localhost:8085")
        print(f"Fleet: {len(positions)} UAVs")
        print(f"Press Ctrl+C to stop")
        print(f"{'='*60}\n")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait()
        print("Stopped")

if __name__ == '__main__':
    main()
