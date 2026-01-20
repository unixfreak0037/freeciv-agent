#!/usr/bin/env python3

import argparse
import asyncio
import os
import sys
import signal

from fc_client.client import FreeCivClient


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="FreeCiv AI client")
    parser.add_argument(
        '--debug-packets',
        metavar='DIR',
        nargs='?',
        const='packets',  # Default when --debug-packets provided without arg
        default=None,     # Default when --debug-packets not provided
        help='Enable packet debugging to DIR (default: packets)'
    )
    return parser.parse_args()


async def main() -> int:
    """
    Main entry point for the FreeCiv AI client.

    Implements an event-driven architecture with:
    - Continuous packet reading loop
    - Signal handling for clean shutdown (SIGINT, SIGTERM)
    - Graceful connection cleanup
    """
    # Parse command-line arguments
    args = parse_args()

    shutdown_event = asyncio.Event()

    # Create client with optional packet debugging
    try:
        client = FreeCivClient(debug_packets_dir=args.debug_packets)
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return os.EX_USAGE  # Exit code 64

    # Setup signal handlers for clean shutdown
    def signal_handler(signum):
        """Handle Unix signals by setting shutdown event"""
        sig_name = signal.Signals(signum).name
        print(f"\nReceived {sig_name}, shutting down gracefully...")
        shutdown_event.set()

    # Get the running event loop
    loop = asyncio.get_running_loop()

    # Register signal handlers with the event loop
    # Handle SIGTERM availability for cross-platform compatibility
    signals = [signal.SIGINT]
    if hasattr(signal, 'SIGTERM'):
        signals.append(signal.SIGTERM)

    for sig in signals:
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        # Connect to server
        await client.connect("192.168.86.33", 6556)

        # Start packet reader task (runs in background)
        await client.start_packet_reader(shutdown_event)

        # Send join request packet
        await client.send_join_request("ai-user")

        # Wait for join to succeed (with timeout)
        try:
            success = await client.wait_for_join(timeout=10.0)
            if not success and not shutdown_event.is_set():
                # Only print timeout if shutdown wasn't already triggered by packet reader
                print("Failed to join game (timeout)")
                shutdown_event.set()
        except asyncio.TimeoutError:
            if not shutdown_event.is_set():
                print("Join timeout")
                shutdown_event.set()

        # Main loop - wait for shutdown event
        if not shutdown_event.is_set():
            print("Connected. Waiting for events... (Ctrl+C to stop)")
            await shutdown_event.wait()

    finally:
        # Clean up
        print("Shutting down...")
        await client.stop_and_disconnect()
        print("Disconnected cleanly")

    return os.EX_OK


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))