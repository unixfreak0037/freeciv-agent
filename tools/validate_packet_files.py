#!/usr/bin/env python3
"""
Packet File Validation Tool

Validates the integrity of captured FreeCiv packet files by verifying that:
1. The length header matches the actual file size
2. Files contain complete packet data as claimed by the header

This tool proves that the packet debugger captures complete raw packet data
without truncation or corruption.

Usage:
    python3 tools/validate_packet_files.py <directory>
    python3 tools/validate_packet_files.py packets/  # Example
"""

import os
import sys
import struct
from pathlib import Path
from typing import List, Tuple, Dict
from collections import defaultdict


class PacketValidationResult:
    """Result of validating a single packet file"""

    def __init__(self, filename: str, packet_type: int, claimed_size: int, actual_size: int):
        self.filename = filename
        self.packet_type = packet_type
        self.claimed_size = claimed_size
        self.actual_size = actual_size
        self.is_valid = claimed_size == actual_size

    def __repr__(self):
        status = "✓ VALID" if self.is_valid else "✗ INVALID"
        return (
            f"{status} | {self.filename:30} | Type {self.packet_type:3} | "
            f"Claimed: {self.claimed_size:5} bytes | Actual: {self.actual_size:5} bytes"
        )


class PacketValidator:
    """Validates captured packet files for integrity"""

    def __init__(self, packet_dir: str):
        self.packet_dir = Path(packet_dir)
        self.results: List[PacketValidationResult] = []
        self.type_counts: Dict[int, int] = defaultdict(int)

    def validate_packet_file(self, filepath: Path) -> PacketValidationResult:
        """
        Validate a single packet file.

        Reads the length header (first 2 bytes as big-endian UINT16) and compares
        it to the actual file size. Also extracts the packet type for reporting.

        Args:
            filepath: Path to the packet file

        Returns:
            PacketValidationResult with validation details
        """
        actual_size = filepath.stat().st_size

        # Read packet header
        with open(filepath, "rb") as f:
            if actual_size < 2:
                # File too small to contain length header
                return PacketValidationResult(
                    filepath.name, packet_type=-1, claimed_size=0, actual_size=actual_size
                )

            # Read length header (2 bytes, big-endian UINT16)
            length_bytes = f.read(2)
            claimed_size = struct.unpack("!H", length_bytes)[0]

            # Read packet type if available (2 bytes for protocol version 2)
            # Note: Version 1 uses 1 byte, but we assume version 2 for most packets
            packet_type = -1
            if actual_size >= 4:
                type_bytes = f.read(2)
                packet_type = struct.unpack("<H", type_bytes)[0]  # Little-endian UINT16

        return PacketValidationResult(filepath.name, packet_type, claimed_size, actual_size)

    def scan_directory(self) -> None:
        """Scan directory and validate all .packet files"""
        if not self.packet_dir.exists():
            print(f"Error: Directory '{self.packet_dir}' does not exist")
            sys.exit(1)

        if not self.packet_dir.is_dir():
            print(f"Error: '{self.packet_dir}' is not a directory")
            sys.exit(1)

        # Find all .packet files
        packet_files = sorted(self.packet_dir.glob("*.packet"))

        if not packet_files:
            print(f"No .packet files found in '{self.packet_dir}'")
            sys.exit(0)

        print(f"Validating {len(packet_files)} packet files in '{self.packet_dir}'...\n")

        # Validate each file
        for filepath in packet_files:
            result = self.validate_packet_file(filepath)
            self.results.append(result)
            self.type_counts[result.packet_type] += 1

    def print_results(self) -> None:
        """Print validation results and summary"""
        print("=" * 100)
        print("VALIDATION RESULTS")
        print("=" * 100)

        # Print individual results
        for result in self.results:
            print(result)

        # Print summary statistics
        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)

        total_packets = len(self.results)
        valid_packets = sum(1 for r in self.results if r.is_valid)
        invalid_packets = total_packets - valid_packets

        print(f"Total packets validated: {total_packets}")
        print(
            f"Valid packets:           {valid_packets} ({100 * valid_packets / total_packets:.1f}%)"
        )
        print(
            f"Invalid packets:         {invalid_packets} ({100 * invalid_packets / total_packets:.1f}%)"
        )

        # Packet type distribution
        print(f"\nPacket type distribution:")
        sorted_types = sorted(self.type_counts.items())
        for packet_type, count in sorted_types:
            if packet_type == -1:
                print(f"  Unknown/Corrupt: {count}")
            else:
                print(f"  Type {packet_type:3}: {count:3} packets")

        # Validation errors detail
        if invalid_packets > 0:
            print(f"\n{'=' * 100}")
            print("VALIDATION ERRORS")
            print("=" * 100)
            for result in self.results:
                if not result.is_valid:
                    size_diff = result.actual_size - result.claimed_size
                    print(f"✗ {result.filename}")
                    print(f"  Claimed size: {result.claimed_size} bytes")
                    print(f"  Actual size:  {result.actual_size} bytes")
                    print(f"  Difference:   {size_diff:+} bytes")
                    if size_diff < 0:
                        print(f"  ⚠ TRUNCATED: File is SMALLER than claimed")
                    else:
                        print(f"  ⚠ OVERSIZED: File is LARGER than claimed")

    def get_exit_code(self) -> int:
        """Return exit code based on validation results"""
        invalid_count = sum(1 for r in self.results if not r.is_valid)
        return 1 if invalid_count > 0 else 0


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tools/validate_packet_files.py <directory>")
        print()
        print("Example:")
        print("  python3 tools/validate_packet_files.py packets/")
        sys.exit(1)

    packet_dir = sys.argv[1]

    validator = PacketValidator(packet_dir)
    validator.scan_directory()
    validator.print_results()

    sys.exit(validator.get_exit_code())


if __name__ == "__main__":
    main()
