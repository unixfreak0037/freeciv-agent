"""
Async tests for fc_client/protocol.py

Tests async I/O functions with mocked StreamReader/StreamWriter.
"""

import asyncio
import struct
import pytest
from unittest.mock import AsyncMock

from fc_client.protocol import (
    _recv_exact,
    read_packet,
)


# ============================================================================
# Helper Functions
# ============================================================================


def setup_mock_reader_sequence(mock_reader, byte_sequences: list):
    """
    Configure mock reader to return a sequence of byte arrays.

    Args:
        mock_reader: Mock StreamReader instance
        byte_sequences: List of byte arrays to return on sequential readexactly() calls
    """
    mock_reader.readexactly = AsyncMock(side_effect=byte_sequences)


# ============================================================================
# Phase 3: Async I/O with Mocked Streams
# ============================================================================


# _recv_exact tests (4 tests)


@pytest.mark.async_test
@pytest.mark.network
async def test_recv_exact_success(mock_stream_reader):
    """Test _recv_exact successfully reads exact number of bytes."""
    # Mock returns 5 bytes
    mock_stream_reader.readexactly = AsyncMock(return_value=b'\x01\x02\x03\x04\x05')

    result = await _recv_exact(mock_stream_reader, 5)

    assert result == b'\x01\x02\x03\x04\x05'
    mock_stream_reader.readexactly.assert_called_once_with(5)


@pytest.mark.async_test
@pytest.mark.network
async def test_recv_exact_incomplete_read(mock_stream_reader):
    """Test _recv_exact raises ConnectionError on incomplete read."""
    # Mock raises IncompleteReadError
    mock_stream_reader.readexactly = AsyncMock(
        side_effect=asyncio.IncompleteReadError(b'\x01', 5)
    )

    with pytest.raises(ConnectionError, match="Socket closed while reading data"):
        await _recv_exact(mock_stream_reader, 5)


@pytest.mark.async_test
@pytest.mark.network
async def test_recv_exact_zero_bytes(mock_stream_reader):
    """Test _recv_exact edge case with 0 bytes requested."""
    mock_stream_reader.readexactly = AsyncMock(return_value=b'')

    result = await _recv_exact(mock_stream_reader, 0)

    assert result == b''
    mock_stream_reader.readexactly.assert_called_once_with(0)


@pytest.mark.async_test
@pytest.mark.network
async def test_recv_exact_large_read(mock_stream_reader):
    """Test _recv_exact with large byte count (10000 bytes)."""
    large_data = b'\xaa' * 10000
    mock_stream_reader.readexactly = AsyncMock(return_value=large_data)

    result = await _recv_exact(mock_stream_reader, 10000)

    assert result == large_data
    assert len(result) == 10000


# read_packet tests (9 tests)


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_one_byte_type_minimal(mock_stream_reader):
    """Test reading minimal packet with 1-byte type and no payload."""
    # Packet: length=3, type=5, no payload
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x03',  # Length = 3
        b'\x05',      # Type = 5 (1 byte)
        b''           # No payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=False)

    assert packet_type == 5
    assert payload == b''
    assert raw_packet == b'\x00\x03\x05'


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_one_byte_type_with_payload(mock_stream_reader):
    """Test reading packet with 1-byte type and 7-byte payload."""
    # Packet: length=10, type=25, payload=7 bytes
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x0a',     # Length = 10
        b'\x19',         # Type = 25 (1 byte)
        b'payload'       # 7-byte payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=False)

    assert packet_type == 25
    assert payload == b'payload'
    assert raw_packet == b'\x00\x0a\x19payload'


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_two_byte_type(mock_stream_reader):
    """Test reading packet with 2-byte type (type > 255)."""
    # Packet: length=4, type=300, no payload
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x04',     # Length = 4
        b'\x01\x2c',     # Type = 300 (2 bytes)
        b''              # No payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=True)

    assert packet_type == 300
    assert payload == b''
    assert raw_packet == b'\x00\x04\x01\x2c'


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_two_byte_type_with_payload(mock_stream_reader):
    """Test reading packet with 2-byte type and payload, verify header_size=4."""
    # Packet: length=12, type=500, payload=8 bytes
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x0c',     # Length = 12
        b'\x01\xf4',     # Type = 500 (2 bytes)
        b'testdata'      # 8-byte payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=True)

    assert packet_type == 500
    assert payload == b'testdata'
    assert len(raw_packet) == 12
    assert raw_packet == b'\x00\x0c\x01\xf4testdata'


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_raw_packet_reconstruction(mock_stream_reader):
    """Test that raw_packet correctly includes complete packet with header."""
    # Packet with known structure
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x08',     # Length = 8
        b'\x0f',         # Type = 15
        b'12345'         # 5-byte payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=False)

    # Verify raw_packet is complete and correct
    assert raw_packet == b'\x00\x08\x0f12345'
    assert len(raw_packet) == 8

    # Verify we can parse the raw packet
    packet_length = struct.unpack('>H', raw_packet[0:2])[0]
    assert packet_length == 8


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_sequential_reads(mock_stream_reader):
    """Test sequential packet reads verify mock call sequence."""
    # First packet
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x03',     # Length
        b'\x01',         # Type
        b''              # No payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=False)
    assert packet_type == 1

    # Second packet (reset mock for new sequence)
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x05',     # Length
        b'\x05',         # Type
        b'ab'            # 2-byte payload
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=False)
    assert packet_type == 5
    assert payload == b'ab'


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_connection_lost_during_length(mock_stream_reader):
    """Test error handling when connection closes during length read."""
    # Connection closes while reading length
    mock_stream_reader.readexactly = AsyncMock(
        side_effect=asyncio.IncompleteReadError(b'\x00', 2)
    )

    with pytest.raises(ConnectionError):
        await read_packet(mock_stream_reader, use_two_byte_type=False)


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_connection_lost_during_payload(mock_stream_reader):
    """Test error handling when connection closes during payload read."""
    # Connection closes while reading payload
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x0a',     # Length = 10 (expects 7 bytes payload)
        b'\x19',         # Type = 25
        # Incomplete payload read
        AsyncMock(side_effect=asyncio.IncompleteReadError(b'pay', 7))()
    ])

    # Use side_effect to handle the sequence properly
    mock_stream_reader.readexactly = AsyncMock(side_effect=[
        b'\x00\x0a',  # Length
        b'\x19',       # Type
        asyncio.IncompleteReadError(b'pay', 7)  # Incomplete payload
    ])

    with pytest.raises(ConnectionError):
        await read_packet(mock_stream_reader, use_two_byte_type=False)


@pytest.mark.async_test
@pytest.mark.network
async def test_read_packet_zero_length_payload(mock_stream_reader):
    """Test reading packet with zero-length payload (edge case)."""
    # Packet with header only, no payload
    setup_mock_reader_sequence(mock_stream_reader, [
        b'\x00\x03',     # Length = 3 (header only)
        b'\xff',         # Type = 255
        b''              # Empty payload (length=0)
    ])

    packet_type, payload, raw_packet = await read_packet(mock_stream_reader, use_two_byte_type=False)

    assert packet_type == 255
    assert payload == b''
    assert len(payload) == 0
    assert raw_packet == b'\x00\x03\xff'
