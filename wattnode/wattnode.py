#!/usr/bin/env python3
"""
WattNode – light node for the WattCoin network.

Commands:
  register <stake_tx>  Register node with the network
  run                   Start the daemon (scrape/inference)
  status                Check node status
  earnings              View earnings summary
  sensor                Start sensor oracle (Raspberry Pi)
"""

import argparse
import sys
import logging

from services.node_service import NodeService
from services.oracle import SensorOracle

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('wattnode')


def main():
    parser = argparse.ArgumentParser(description='WattNode light node')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # register
    reg_parser = subparsers.add_parser('register', help='Register node with network')
    reg_parser.add_argument('stake_tx', help='Transaction signature for 10,000 WATT stake')

    # run
    subparsers.add_parser('run', help='Start the node daemon')

    # status
    subparsers.add_parser('status', help='Check node registration or status')

    # earnings
    subparsers.add_parser('earnings', help='View earnings summary')

    # sensor
    sensor_parser = subparsers.add_parser('sensor', help='Start sensor oracle (Raspberry Pi)')
    sensor_parser.add_argument('--config', default=None, help='Path to config.yaml')
    sensor_parser.add_argument('--mock', action='store_true', help='Force mock sensors')
    sensor_parser.add_argument('--interval', type=int, default=None, help='Reporting interval in seconds')
    sensor_parser.add_argument('--once', action='store_true', help='Read sensors once and exit')

    args = parser.parse_args()

    if args.command == 'register':
        service = NodeService()
        service.register(args.stake_tx)
    elif args.command == 'run':
        service = NodeService()
        service.run()
    elif args.command == 'status':
        service = NodeService()
        service.status()
    elif args.command == 'earnings':
        service = NodeService()
        service.earnings()
    elif args.command == 'sensor':
        oracle = SensorOracle(config_path=args.config)
        if args.mock:
            oracle.config.setdefault('oracle', {})['mock'] = True
        if args.interval:
            oracle.config.setdefault('oracle', {})['interval'] = args.interval
        if args.once:
            readings = oracle.read_all_sensors()
            if readings:
                oracle.report(readings)
            else:
                print('No sensor readings.')
        else:
            oracle.run()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
