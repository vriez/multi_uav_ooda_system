#!/usr/bin/env python3
"""
Launch script for UAV fleet demonstration
"""
import subprocess
import time
import sys
import os

def launch_gcs():
    """Launch Ground Control Station"""
    print("Starting GCS...")
    return subprocess.Popen(
        [sys.executable, '-m', 'gcs.main'],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

def launch_uav(uav_id, x, y, z=10):
    """Launch single UAV"""
    print(f"Starting UAV {uav_id} at ({x}, {y}, {z})")
    return subprocess.Popen(
        [sys.executable, '-m', 'uav.client', str(uav_id), str(x), str(y), str(z)],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

def main():
    """Launch complete system"""
    processes = []
    
    try:
        # Start GCS
        gcs = launch_gcs()
        processes.append(gcs)
        time.sleep(2)  # Wait for GCS to start
        
        # Start UAV fleet
        uav_positions = [
            (0, 0, 10),
            (20, 0, 10),
            (40, 0, 10),
            (0, 20, 10),
            (20, 20, 10)
        ]
        
        for i, (x, y, z) in enumerate(uav_positions, start=1):
            uav = launch_uav(i, x, y, z)
            processes.append(uav)
            time.sleep(0.5)
        
        print(f"\nSystem running: 1 GCS + {len(uav_positions)} UAVs")
        print("Press Ctrl+C to stop all processes\n")
        
        # Wait for interruption
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down system...")
        for p in processes:
            p.terminate()
        
        for p in processes:
            p.wait()
        
        print("System stopped")

if __name__ == '__main__':
    main()
