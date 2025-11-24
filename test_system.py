#!/usr/bin/env python3
"""
Quick system test
"""
import sys
sys.path.insert(0, '.')

print("Testing imports...")
try:
    from gcs.ooda_engine import OODAEngine
    from gcs.fleet_monitor import FleetMonitor
    from gcs.constraint_validator import ConstraintValidator
    from gcs.mission_manager import MissionDatabase
    from uav.simulation import UAVSimulation
    print("✓ All imports successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

print("\nTesting configuration...")
try:
    import yaml
    with open('config/gcs_config.yaml') as f:
        gcs_config = yaml.safe_load(f)
    with open('config/uav_config.yaml') as f:
        uav_config = yaml.safe_load(f)
    print("✓ Configuration files valid")
except Exception as e:
    print(f"✗ Config failed: {e}")
    sys.exit(1)

print("\nTesting OODA engine...")
try:
    engine = OODAEngine(gcs_config)
    print(f"✓ OODA engine initialized")
except Exception as e:
    print(f"✗ OODA engine failed: {e}")
    sys.exit(1)

print("\nTesting UAV simulation...")
try:
    import numpy as np
    uav = UAVSimulation(1, uav_config, np.array([0, 0, 10]))
    telemetry = uav.get_telemetry()
    print(f"✓ UAV simulation working: {telemetry['uav_id']}")
except Exception as e:
    print(f"✗ UAV simulation failed: {e}")
    sys.exit(1)

print("\n" + "="*50)
print("All tests passed! System ready to run.")
print("="*50)
print("\nNext steps:")
print("1. Run: python launch.py")
print("2. Or manually: python -m gcs.main")
print("3. Then: python -m uav.client <id> <x> <y> <z>")
