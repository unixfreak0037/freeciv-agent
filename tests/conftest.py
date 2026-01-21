"""
Shared pytest fixtures for FreeCiv AI client tests.

This module provides reusable fixtures for:
- Mock network streams (StreamReader/StreamWriter)
- Component instances (DeltaCache, GameState, FreeCivClient)
- Sample packet data
- Utility helpers
"""

import asyncio
from typing import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from fc_client.delta_cache import DeltaCache
from fc_client.game_state import GameState


# ============================================================================
# Mock Network Stream Fixtures
# ============================================================================


@pytest.fixture
def mock_stream_reader():
    """
    Mock asyncio.StreamReader for testing packet reading.

    Usage:
        def test_read(mock_stream_reader):
            mock_stream_reader.readexactly = AsyncMock(return_value=b'\\x01\\x02')
            data = await read_packet(mock_stream_reader)
    """
    reader = AsyncMock(spec=asyncio.StreamReader)
    reader.readexactly = AsyncMock()
    reader.read = AsyncMock()
    reader.at_eof = MagicMock(return_value=False)
    return reader


@pytest.fixture
def mock_stream_writer():
    """
    Mock asyncio.StreamWriter for testing packet writing.

    Usage:
        def test_write(mock_stream_writer):
            await send_packet(mock_stream_writer, packet_data)
            mock_stream_writer.write.assert_called_once()
            mock_stream_writer.drain.assert_called_once()
    """
    writer = AsyncMock(spec=asyncio.StreamWriter)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    writer.is_closing = MagicMock(return_value=False)
    return writer


@pytest.fixture
def mock_stream_pair(mock_stream_reader, mock_stream_writer):
    """
    Convenience fixture providing both reader and writer.

    Usage:
        def test_io(mock_stream_pair):
            reader, writer = mock_stream_pair
            # Test read/write operations
    """
    return (mock_stream_reader, mock_stream_writer)


# ============================================================================
# Component Instance Fixtures
# ============================================================================


@pytest.fixture
def delta_cache():
    """
    Fresh DeltaCache instance for testing delta protocol.

    Usage:
        def test_cache(delta_cache):
            delta_cache.update(25, 0, {'turn': 1})
            assert delta_cache.get(25, 0) == {'turn': 1}
    """
    return DeltaCache()


@pytest.fixture
def game_state():
    """
    Fresh GameState instance for testing state tracking.

    Usage:
        def test_state(game_state):
            game_state.update_server_info({'turn': 42})
            assert game_state.server_info['turn'] == 42
    """
    return GameState()


@pytest.fixture
def freeciv_client(mock_stream_reader, mock_stream_writer, delta_cache, game_state):
    """
    Mock FreeCivClient instance with dependencies injected.

    Note: This creates a client with mocked network streams but does NOT
    call connect(). Tests should manually set reader/writer if needed.

    Usage:
        async def test_client(freeciv_client):
            # Client has mocked dependencies but no active connection
            freeciv_client.reader = mock_stream_reader
            freeciv_client.writer = mock_stream_writer
            # Test client methods
    """
    # Import here to avoid circular dependency issues
    from fc_client.client import FreeCivClient

    client = FreeCivClient(host="localhost", port=6556, username="test-user")
    # Inject mocked dependencies
    client.delta_cache = delta_cache
    client.game_state = game_state
    # Don't set reader/writer - let tests control when/how they're set
    return client


# ============================================================================
# Sample Packet Data Fixtures
# ============================================================================


@pytest.fixture
def sample_join_reply_success():
    """
    Sample SERVER_JOIN_REPLY packet data (successful join).

    Packet type 5, success=True, message="Welcome!", capability="+Freeciv..."
    """
    return {
        'you_can_join': True,
        'message': 'Welcome!',
        'capability': '+Freeciv-3.0-network',
        'challenge_file': '',
        'conn_id': 1,
    }


@pytest.fixture
def sample_join_reply_failure():
    """
    Sample SERVER_JOIN_REPLY packet data (failed join).

    Packet type 5, success=False, message="Server full"
    """
    return {
        'you_can_join': False,
        'message': 'Server full',
        'capability': '+Freeciv-3.0-network',
        'challenge_file': '',
        'conn_id': 0,
    }


@pytest.fixture
def sample_server_info():
    """
    Sample SERVER_INFO packet data.

    Packet type 25 with typical game state fields.
    """
    return {
        'turn': 42,
        'year': 1850,
        'phase': 0,  # Movement phase
        'num_players': 4,
        'timeout': 0,
    }


@pytest.fixture
def sample_chat_msg_payload():
    """
    Sample CHAT_MSG packet data.

    Packet type 29 with server message.
    """
    return {
        'message': 'Welcome to FreeCiv!',
        'conn_id': -1,  # Server message
        'event': 0,
    }


# ============================================================================
# Utility Helper Fixtures
# ============================================================================


@pytest.fixture
def packet_builder() -> Callable[[int, int, bytes], bytes]:
    """
    Helper function to build raw packet bytes for testing.

    Returns a function: build_packet(packet_type: int, length: int, body: bytes) -> bytes

    Usage:
        def test_decode(packet_builder):
            packet = packet_builder(5, 100, b'...')
            result = decode_packet(packet)
    """
    def build_packet(packet_type: int, length: int, body: bytes) -> bytes:
        """
        Build a raw packet with header + body.

        Args:
            packet_type: Packet type number (0-65535)
            length: Total packet length including header
            body: Packet body bytes

        Returns:
            Complete packet bytes with length header + type + body
        """
        # Length field (2 bytes, big-endian)
        length_bytes = length.to_bytes(2, byteorder='big')

        # Packet type (1 or 2 bytes depending on protocol version)
        if packet_type <= 255:
            type_bytes = packet_type.to_bytes(1, byteorder='big')
        else:
            type_bytes = packet_type.to_bytes(2, byteorder='big')

        return length_bytes + type_bytes + body

    return build_packet


@pytest.fixture
def sample_bitvector():
    """
    Sample bitvector for testing delta protocol.

    Returns bytes with specific bit pattern: 0b10110100 (bits 2,4,5,7 set)
    """
    return b'\xb4'  # 10110100 in binary


# ============================================================================
# Async Event Loop Configuration
# ============================================================================

# Note: pytest-asyncio with asyncio_mode="auto" handles event loop creation
# automatically. No need for manual event_loop fixture.
