"""
Unit tests for PacketDebugger - FreeCiv packet capture utility.

Tests the debug utility that captures raw packets to disk for protocol analysis.
"""

import pytest
import os
import tempfile
from pathlib import Path

from fc_client.packet_debugger import PacketDebugger


# ============================================================================
# Initialization Tests
# ============================================================================


@pytest.mark.unit
def test_packet_debugger_creates_directory(tmp_path):
    """PacketDebugger should create debug directory if it doesn't exist."""
    debug_dir = tmp_path / "debug"

    debugger = PacketDebugger(str(debug_dir))

    assert debug_dir.exists()
    assert debug_dir.is_dir()


@pytest.mark.unit
def test_packet_debugger_initializes_counters(tmp_path):
    """PacketDebugger should initialize counters to 0."""
    debug_dir = tmp_path / "debug"

    debugger = PacketDebugger(str(debug_dir))

    # Counters are private, but we can verify by checking first file names
    assert debugger._inbound_counter == 0
    assert debugger._outbound_counter == 0


# ============================================================================
# write_inbound_packet Tests
# ============================================================================


@pytest.mark.unit
def test_write_inbound_packet_creates_file(tmp_path):
    """write_inbound_packet should create numbered packet file."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    packet_data = b"\x00\x05\x00\x01\x02"
    debugger.write_inbound_packet(packet_data, packet_type=5)

    # Should create inbound_0001_type005.packet (counter starts at 0, increments before writing)
    packet_file = debug_dir / "inbound_0001_type005.packet"
    assert packet_file.exists()


@pytest.mark.unit
def test_write_inbound_packet_correct_content(tmp_path):
    """write_inbound_packet should write exact packet bytes."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    packet_data = b"\x00\x05\x00\x01\x02\x03\x04"
    debugger.write_inbound_packet(packet_data, packet_type=25)

    packet_file = debug_dir / "inbound_0001_type025.packet"
    with open(packet_file, 'rb') as f:
        content = f.read()

    assert content == packet_data


@pytest.mark.unit
def test_write_inbound_packet_increments_counter(tmp_path):
    """write_inbound_packet should increment counter for each packet."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    # Write multiple packets
    debugger.write_inbound_packet(b"\x01", packet_type=5)
    debugger.write_inbound_packet(b"\x02", packet_type=25)
    debugger.write_inbound_packet(b"\x03", packet_type=29)

    # Should have files numbered 1, 2, 3
    assert (debug_dir / "inbound_0001_type005.packet").exists()
    assert (debug_dir / "inbound_0002_type025.packet").exists()
    assert (debug_dir / "inbound_0003_type029.packet").exists()


@pytest.mark.unit
def test_write_inbound_packet_empty_data(tmp_path):
    """write_inbound_packet should handle empty packet data."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    debugger.write_inbound_packet(b"", packet_type=0)

    packet_file = debug_dir / "inbound_0001_type000.packet"
    assert packet_file.exists()

    # File should be empty
    assert packet_file.stat().st_size == 0


# ============================================================================
# write_outbound_packet Tests
# ============================================================================


@pytest.mark.unit
def test_write_outbound_packet_creates_file(tmp_path):
    """write_outbound_packet should create numbered packet file."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    packet_data = b"\x00\x05\x04\x01\x02"
    debugger.write_outbound_packet(packet_data, packet_type=4)

    # Should create outbound_0001_type004.packet
    packet_file = debug_dir / "outbound_0001_type004.packet"
    assert packet_file.exists()


@pytest.mark.unit
def test_write_outbound_packet_correct_content(tmp_path):
    """write_outbound_packet should write exact packet bytes."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    packet_data = b"\x00\x0a\x04\x01\x02\x03\x04\x05\x06\x07"
    debugger.write_outbound_packet(packet_data, packet_type=4)

    packet_file = debug_dir / "outbound_0001_type004.packet"
    with open(packet_file, 'rb') as f:
        content = f.read()

    assert content == packet_data


@pytest.mark.unit
def test_write_outbound_packet_increments_counter(tmp_path):
    """write_outbound_packet should increment counter for each packet."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    # Write multiple packets
    debugger.write_outbound_packet(b"\x01", packet_type=4)
    debugger.write_outbound_packet(b"\x02", packet_type=4)
    debugger.write_outbound_packet(b"\x03", packet_type=4)

    # Should have files numbered 1, 2, 3
    assert (debug_dir / "outbound_0001_type004.packet").exists()
    assert (debug_dir / "outbound_0002_type004.packet").exists()
    assert (debug_dir / "outbound_0003_type004.packet").exists()


# ============================================================================
# Counter Independence Tests
# ============================================================================


@pytest.mark.unit
def test_inbound_outbound_counters_independent(tmp_path):
    """Inbound and outbound counters should be independent."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    # Write some inbound packets
    debugger.write_inbound_packet(b"\x01", packet_type=5)
    debugger.write_inbound_packet(b"\x02", packet_type=25)

    # Write some outbound packets
    debugger.write_outbound_packet(b"\x03", packet_type=4)

    # Both should start from 1
    assert (debug_dir / "inbound_0001_type005.packet").exists()
    assert (debug_dir / "inbound_0002_type025.packet").exists()
    assert (debug_dir / "outbound_0001_type004.packet").exists()


@pytest.mark.unit
def test_interleaved_inbound_outbound_writes(tmp_path):
    """Interleaved writes should maintain separate counters."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    # Interleave writes
    debugger.write_outbound_packet(b"\xa1", packet_type=4)
    debugger.write_inbound_packet(b"\xb1", packet_type=5)
    debugger.write_outbound_packet(b"\xa2", packet_type=4)
    debugger.write_inbound_packet(b"\xb2", packet_type=25)
    debugger.write_outbound_packet(b"\xa3", packet_type=4)

    # Check files exist with correct counters
    assert (debug_dir / "outbound_0001_type004.packet").exists()
    assert (debug_dir / "outbound_0002_type004.packet").exists()
    assert (debug_dir / "outbound_0003_type004.packet").exists()
    assert (debug_dir / "inbound_0001_type005.packet").exists()
    assert (debug_dir / "inbound_0002_type025.packet").exists()

    # Verify content to ensure correct packet went to correct file
    with open(debug_dir / "outbound_0001_type004.packet", 'rb') as f:
        assert f.read() == b"\xa1"
    with open(debug_dir / "inbound_0001_type005.packet", 'rb') as f:
        assert f.read() == b"\xb1"


# ============================================================================
# Binary Data Tests
# ============================================================================


@pytest.mark.unit
def test_write_inbound_packet_binary_data(tmp_path):
    """write_inbound_packet should handle binary data correctly."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    # Binary data with all byte values
    packet_data = bytes(range(256))
    debugger.write_inbound_packet(packet_data, packet_type=29)

    packet_file = debug_dir / "inbound_0001_type029.packet"
    with open(packet_file, 'rb') as f:
        content = f.read()

    assert content == packet_data
    assert len(content) == 256


@pytest.mark.unit
def test_write_outbound_packet_large_data(tmp_path):
    """write_outbound_packet should handle large packets."""
    debug_dir = tmp_path / "debug"
    debugger = PacketDebugger(str(debug_dir))

    # Large packet (10KB)
    packet_data = b"\xff" * 10240
    debugger.write_outbound_packet(packet_data, packet_type=100)

    packet_file = debug_dir / "outbound_0001_type100.packet"
    assert packet_file.stat().st_size == 10240

    with open(packet_file, 'rb') as f:
        content = f.read()

    assert content == packet_data


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.unit
def test_packet_debugger_with_nested_directory(tmp_path):
    """PacketDebugger should handle nested directory paths."""
    debug_dir = tmp_path / "level1" / "level2" / "debug"

    debugger = PacketDebugger(str(debug_dir))

    assert debug_dir.exists()
    debugger.write_inbound_packet(b"\x01", packet_type=5)
    assert (debug_dir / "inbound_0001_type005.packet").exists()


@pytest.mark.unit
def test_multiple_debuggers_same_parent(tmp_path):
    """Multiple debuggers can coexist in sibling directories."""
    debug_dir1 = tmp_path / "debug1"
    debug_dir2 = tmp_path / "debug2"

    debugger1 = PacketDebugger(str(debug_dir1))
    debugger2 = PacketDebugger(str(debug_dir2))

    debugger1.write_inbound_packet(b"\x01", packet_type=5)
    debugger2.write_inbound_packet(b"\x02", packet_type=25)

    assert (debug_dir1 / "inbound_0001_type005.packet").exists()
    assert (debug_dir2 / "inbound_0001_type025.packet").exists()

    # Verify content is different
    with open(debug_dir1 / "inbound_0001_type005.packet", 'rb') as f:
        assert f.read() == b"\x01"
    with open(debug_dir2 / "inbound_0001_type025.packet", 'rb') as f:
        assert f.read() == b"\x02"
