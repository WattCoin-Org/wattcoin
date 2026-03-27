#!/usr/bin/env python3
"""
IoT Bridge CLI — Control smart home devices via WattCoin network.

Usage:
    python iot_bridge_cli.py config.yaml              # Start bridge
    python iot_bridge_cli.py config.yaml discover   # Discover devices
    python iot_bridge_cli.py config.yaml list        # List devices & states
    python iot_bridge_cli.py config.yaml on <id>   # Turn on device
    python iot_bridge_cli.py config.yaml off <id>  # Turn off device
    python iot_bridge_cli.py config.yaml brightness <id> <level>  # Set brightness
"""
import sys
import time
import yaml
import argparse

from iot_bridge.bridge import IoTBridge


def cmd_discover(bridge: IoTBridge):
    devices = bridge.discover_devices()
    print(f"Found {len(devices)} devices:")
    for d in devices:
        state = bridge.get_device_state(d["id"])
        state_str = f"state={state.get('state', '?')}" if state else "no state"
        print(f"  [{d['id']}] {d['name']} ({d['type']}) — {state_str}")


def cmd_list(bridge: IoTBridge):
    states = bridge.get_all_states()
    print(f"Device states ({len(states)} devices):")
    for device_id, state in states.items():
        print(f"  [{device_id}] {state}")


def cmd_on(bridge: IoTBridge, device_id: str):
    result = bridge.send_command(device_id, "on", {})
    print(f"ON {device_id}: {'OK' if result.get('success') else 'FAILED'} — {result}")


def cmd_off(bridge: IoTBridge, device_id: str):
    result = bridge.send_command(device_id, "off", {})
    print(f"OFF {device_id}: {'OK' if result.get('success') else 'FAILED'} — {result}")


def cmd_brightness(bridge: IoTBridge, device_id: str, level: int):
    result = bridge.send_command(device_id, "brightness", {"brightness": int(level)})
    print(f"Brightness {device_id} -> {level}: {'OK' if result.get('success') else 'FAILED'}")


def main():
    parser = argparse.ArgumentParser(description="WattCoin IoT Bridge CLI")
    parser.add_argument("config", help="Path to config.yaml")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["discover", "list", "on", "off", "brightness", "run"])
    parser.add_argument("device_id", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()

    try:
        with open(args.config) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    bridge = IoTBridge(config)

    if args.command == "discover":
        cmd_discover(bridge)
    elif args.command == "list":
        cmd_list(bridge)
    elif args.command == "on":
        if not args.device_id:
            print("Usage: on <device_id>")
            sys.exit(1)
        cmd_on(bridge, args.device_id)
    elif args.command == "off":
        if not args.device_id:
            print("Usage: off <device_id>")
            sys.exit(1)
        cmd_off(bridge, args.device_id)
    elif args.command == "brightness":
        if not args.device_id or not args.value:
            print("Usage: brightness <device_id> <level>")
            sys.exit(1)
        cmd_brightness(bridge, args.device_id, args.value)
    elif args.command == "run":
        print("Starting WattCoin IoT Bridge...")
        devices = bridge.discover_devices()
        print(f"Discovered {len(devices)} devices:")
        for d in devices:
            print(f"  [{d['id']}] {d['name']} ({d['type']})")
        bridge.start()
        print("Bridge running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping bridge...")
            bridge.stop()
            print("Stopped.")


if __name__ == "__main__":
    main()
