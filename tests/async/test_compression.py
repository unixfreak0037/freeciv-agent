"""
Tests for FreeCiv packet compression system.

This module tests the compression detection, decompression, and buffer parsing
functionality added to the protocol layer to support FreeCiv's DEFLATE-based
packet compression system.
"""

import asyncio
import struct
import zlib
import pytest
from unittest.mock import AsyncMock

from fc_client.protocol import (
    read_packet,
    _decompress_packet,
    _parse_packet_buffer,
    COMPRESSION_BORDER,
    JUMBO_SIZE,
    JUMBO_BORDER,
)


# ============================================================================
# Test Fixtures and Helpers
# ============================================================================

def make_uncompressed_packet(packet_type: int, payload: bytes, use_two_byte_type: bool = False) -> bytes:
    """Create an uncompressed packet with proper header."""
    if use_two_byte_type:
        header_size = 4
        type_bytes = struct.pack('>H', packet_type)
    else:
        header_size = 3
        type_bytes = struct.pack('B', packet_type)

    packet_length = header_size + len(payload)
    length_bytes = struct.pack('>H', packet_length)

    return length_bytes + type_bytes + payload


def make_compressed_packet(packets_data: list[bytes], force_jumbo: bool = False) -> bytes:
    """
    Create compressed packet for testing.

    Args:
        packets_data: List of complete packet bytes (with headers) to compress
        force_jumbo: If True, use JUMBO format regardless of size

    Returns:
        Complete compressed packet bytes
    """
    # Concatenate packets
    decompressed_buffer = b''.join(packets_data)

    # Compress
    compressed_data = zlib.compress(decompressed_buffer)
    compressed_size = len(compressed_data)

    # Build header
    if force_jumbo or compressed_size + 2 > JUMBO_BORDER:
        # JUMBO format: [0xFFFF] [4-byte actual_length] [compressed_data]
        actual_length = compressed_size + 6
        header = struct.pack('>H', JUMBO_SIZE) + struct.pack('>I', actual_length)
    else:
        # Normal compressed: [2-byte (length + COMPRESSION_BORDER)] [compressed_data]
        length = compressed_size + COMPRESSION_BORDER
        header = struct.pack('>H', length)

    return header + compressed_data


@pytest.fixture
def mock_reader():
    """Create a mock StreamReader for testing."""
    reader = AsyncMock(spec=asyncio.StreamReader)
    return reader


# ============================================================================
# Unit Tests - Decompression and Buffer Parsing
# ============================================================================

def test_decompress_packet_valid():
    """Test decompression with valid zlib data."""
    original_data = b"Hello, FreeCiv!" * 10
    compressed = zlib.compress(original_data)

    result = _decompress_packet(compressed)

    assert result == original_data


def test_decompress_packet_empty():
    """Test decompression with empty data."""
    compressed = zlib.compress(b"")

    result = _decompress_packet(compressed)

    assert result == b""


def test_decompress_packet_corrupt():
    """Test decompression with corrupt data raises ValueError."""
    corrupt_data = b"\x00\x01\x02\x03\x04\x05"

    with pytest.raises(ValueError, match="Decompression failed"):
        _decompress_packet(corrupt_data)


@pytest.mark.asyncio
async def test_parse_packet_buffer_single_1byte():
    """Test parsing buffer with single packet using 1-byte type."""
    # Create a packet: type=5, payload="test"
    packet = make_uncompressed_packet(5, b"test", use_two_byte_type=False)

    result = await _parse_packet_buffer(packet, use_two_byte_type=False)

    assert len(result) == 1
    assert result[0][0] == 5  # packet_type
    assert result[0][1] == b"test"  # payload
    assert result[0][2] == packet  # raw_packet


@pytest.mark.asyncio
async def test_parse_packet_buffer_single_2byte():
    """Test parsing buffer with single packet using 2-byte type."""
    # Create a packet: type=300, payload="test"
    packet = make_uncompressed_packet(300, b"test", use_two_byte_type=True)

    result = await _parse_packet_buffer(packet, use_two_byte_type=True)

    assert len(result) == 1
    assert result[0][0] == 300  # packet_type
    assert result[0][1] == b"test"  # payload
    assert result[0][2] == packet  # raw_packet


@pytest.mark.asyncio
async def test_parse_packet_buffer_multiple():
    """Test parsing buffer with multiple packets."""
    packet1 = make_uncompressed_packet(5, b"first", use_two_byte_type=False)
    packet2 = make_uncompressed_packet(10, b"second", use_two_byte_type=False)
    packet3 = make_uncompressed_packet(15, b"third", use_two_byte_type=False)

    buffer = packet1 + packet2 + packet3

    result = await _parse_packet_buffer(buffer, use_two_byte_type=False)

    assert len(result) == 3
    assert result[0][0] == 5
    assert result[0][1] == b"first"
    assert result[1][0] == 10
    assert result[1][1] == b"second"
    assert result[2][0] == 15
    assert result[2][1] == b"third"


@pytest.mark.asyncio
async def test_parse_packet_buffer_empty():
    """Test parsing empty buffer returns empty list."""
    result = await _parse_packet_buffer(b"", use_two_byte_type=False)

    assert result == []


@pytest.mark.asyncio
async def test_parse_packet_buffer_incomplete_header():
    """Test parsing buffer with incomplete header raises ValueError."""
    # Only 2 bytes (need at least 3 for 1-byte type)
    incomplete = b"\x00\x05"

    with pytest.raises(ValueError, match="Incomplete packet header"):
        await _parse_packet_buffer(incomplete, use_two_byte_type=False)


@pytest.mark.asyncio
async def test_parse_packet_buffer_incomplete_payload():
    """Test parsing buffer with incomplete payload raises ValueError."""
    # Header says length=10, but payload is shorter
    incomplete = struct.pack('>H', 10) + struct.pack('B', 5) + b"short"

    with pytest.raises(ValueError, match="Incomplete packet"):
        await _parse_packet_buffer(incomplete, use_two_byte_type=False)


@pytest.mark.asyncio
async def test_parse_packet_buffer_invalid_length():
    """Test parsing buffer with invalid length raises ValueError."""
    # Length=2 is less than header size (3)
    invalid = struct.pack('>H', 2) + struct.pack('B', 5)

    with pytest.raises(ValueError, match="Invalid packet length"):
        await _parse_packet_buffer(invalid, use_two_byte_type=False)


# ============================================================================
# Async Tests - read_packet() with Compression
# ============================================================================

@pytest.mark.asyncio
async def test_read_packet_uncompressed_unchanged(mock_reader):
    """Test that uncompressed packets still work after compression code added."""
    # Create uncompressed packet: type=5, payload="hello"
    packet = make_uncompressed_packet(5, b"hello", use_two_byte_type=False)

    # Mock reader to return packet bytes
    mock_reader.readexactly = AsyncMock(side_effect=[
        packet[0:2],   # length bytes
        packet[2:3],   # type byte
        packet[3:]     # payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_reader, use_two_byte_type=False)

    assert packet_type == 5
    assert payload == b"hello"
    assert raw_packet == packet


@pytest.mark.asyncio
async def test_read_packet_normal_compressed(mock_reader):
    """Test reading normal compressed packet (length >= COMPRESSION_BORDER)."""
    # Create a packet to compress
    inner_packet = make_uncompressed_packet(25, b"compressed data", use_two_byte_type=False)
    compressed_packet = make_compressed_packet([inner_packet], force_jumbo=False)

    # Mock reader to return compressed packet bytes
    length_bytes = compressed_packet[0:2]
    compressed_data = compressed_packet[2:]

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,      # length field (>= COMPRESSION_BORDER)
        compressed_data    # compressed data
    ])

    packet_type, payload, raw_packet = await read_packet(mock_reader, use_two_byte_type=False)

    assert packet_type == 25
    assert payload == b"compressed data"


@pytest.mark.asyncio
async def test_read_packet_jumbo_compressed(mock_reader):
    """Test reading JUMBO compressed packet (length == JUMBO_SIZE)."""
    # Create a large packet to compress
    large_payload = b"X" * 10000
    inner_packet = make_uncompressed_packet(30, large_payload, use_two_byte_type=False)
    compressed_packet = make_compressed_packet([inner_packet], force_jumbo=True)

    # Mock reader to return JUMBO compressed packet bytes
    length_bytes = compressed_packet[0:2]  # Should be 0xFFFF
    actual_length_bytes = compressed_packet[2:6]
    compressed_data = compressed_packet[6:]

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,          # JUMBO_SIZE marker
        actual_length_bytes,   # 4-byte actual length
        compressed_data        # compressed data
    ])

    packet_type, payload, raw_packet = await read_packet(mock_reader, use_two_byte_type=False)

    assert packet_type == 30
    assert payload == large_payload


@pytest.mark.asyncio
async def test_read_packet_compressed_2byte_type(mock_reader):
    """Test compressed packet with 2-byte type field."""
    # Create packet with type > 255
    inner_packet = make_uncompressed_packet(300, b"data", use_two_byte_type=True)
    compressed_packet = make_compressed_packet([inner_packet], force_jumbo=False)

    length_bytes = compressed_packet[0:2]
    compressed_data = compressed_packet[2:]

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,
        compressed_data
    ])

    packet_type, payload, raw_packet = await read_packet(mock_reader, use_two_byte_type=True)

    assert packet_type == 300
    assert payload == b"data"


@pytest.mark.asyncio
async def test_read_packet_compressed_multiple_raises(mock_reader):
    """Test that compressed packet with multiple packets raises NotImplementedError."""
    # Create multiple packets
    packet1 = make_uncompressed_packet(10, b"first", use_two_byte_type=False)
    packet2 = make_uncompressed_packet(20, b"second", use_two_byte_type=False)
    compressed_packet = make_compressed_packet([packet1, packet2], force_jumbo=False)

    length_bytes = compressed_packet[0:2]
    compressed_data = compressed_packet[2:]

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,
        compressed_data
    ])

    with pytest.raises(NotImplementedError, match="multi-packet buffering not implemented"):
        await read_packet(mock_reader, use_two_byte_type=False)


@pytest.mark.asyncio
async def test_read_packet_decompression_error(mock_reader):
    """Test that decompression error raises ConnectionError."""
    # Create packet with corrupt compressed data
    length = COMPRESSION_BORDER + 10
    length_bytes = struct.pack('>H', length)
    corrupt_data = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09"

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,
        corrupt_data
    ])

    with pytest.raises(ConnectionError, match="Decompression failed"):
        await read_packet(mock_reader, use_two_byte_type=False)


@pytest.mark.asyncio
async def test_read_packet_compressed_empty_buffer(mock_reader):
    """Test that compressed packet with empty buffer raises ValueError."""
    # Create compressed packet with empty decompressed buffer
    compressed_data = zlib.compress(b"")
    length = COMPRESSION_BORDER + len(compressed_data)
    length_bytes = struct.pack('>H', length)

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,
        compressed_data
    ])

    with pytest.raises(ValueError, match="contained no packets"):
        await read_packet(mock_reader, use_two_byte_type=False)


@pytest.mark.asyncio
async def test_read_packet_validate_compressed(mock_reader, capsys):
    """Test that validate flag works with compressed packets."""
    inner_packet = make_uncompressed_packet(25, b"test", use_two_byte_type=False)
    compressed_packet = make_compressed_packet([inner_packet], force_jumbo=False)

    length_bytes = compressed_packet[0:2]
    compressed_data = compressed_packet[2:]

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,
        compressed_data
    ])

    await read_packet(mock_reader, use_two_byte_type=False, validate=True)

    captured = capsys.readouterr()
    assert "[VALIDATE]" in captured.out
    assert "Compressed:" in captured.out


# ============================================================================
# Edge Cases and Boundary Conditions
# ============================================================================

@pytest.mark.asyncio
async def test_read_packet_compression_border_minus_one(mock_reader):
    """Test packet with length = COMPRESSION_BORDER - 1 (uncompressed)."""
    # Length just below compression border should be uncompressed
    payload = b"X" * (COMPRESSION_BORDER - 4)  # Account for header
    packet = make_uncompressed_packet(10, payload, use_two_byte_type=False)

    mock_reader.readexactly = AsyncMock(side_effect=[
        packet[0:2],   # length bytes
        packet[2:3],   # type byte
        packet[3:]     # payload
    ])

    packet_type, returned_payload, raw_packet = await read_packet(mock_reader, use_two_byte_type=False)

    assert packet_type == 10
    assert returned_payload == payload


@pytest.mark.asyncio
async def test_read_packet_compression_border_exact(mock_reader):
    """Test packet with length = COMPRESSION_BORDER (compressed)."""
    # This should trigger compression path
    inner_packet = make_uncompressed_packet(15, b"compressed", use_two_byte_type=False)
    compressed_data = zlib.compress(inner_packet)

    # Manually create packet at exact COMPRESSION_BORDER
    length_bytes = struct.pack('>H', COMPRESSION_BORDER)

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,
        compressed_data
    ])

    packet_type, payload, raw_packet = await read_packet(mock_reader, use_two_byte_type=False)

    assert packet_type == 15
    assert payload == b"compressed"


@pytest.mark.asyncio
async def test_read_packet_jumbo_size_exact(mock_reader):
    """Test packet with length = JUMBO_SIZE triggers JUMBO path."""
    inner_packet = make_uncompressed_packet(20, b"jumbo", use_two_byte_type=False)
    compressed_data = zlib.compress(inner_packet)

    # JUMBO format
    length_bytes = struct.pack('>H', JUMBO_SIZE)
    actual_length = len(compressed_data) + 6
    actual_length_bytes = struct.pack('>I', actual_length)

    mock_reader.readexactly = AsyncMock(side_effect=[
        length_bytes,
        actual_length_bytes,
        compressed_data
    ])

    packet_type, payload, raw_packet = await read_packet(mock_reader, use_two_byte_type=False)

    assert packet_type == 20
    assert payload == b"jumbo"
