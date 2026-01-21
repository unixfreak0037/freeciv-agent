"""
Async tests for FreeCivClient - Main client class async methods.

Tests async operations like connect, disconnect, packet reading, and event handling.
"""

import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytest
import tempfile
import os

from fc_client.client import FreeCivClient
from fc_client.game_state import GameState
from fc_client import protocol, handlers


# ============================================================================
# Initialization Tests
# ============================================================================


@pytest.mark.async_test
async def test_client_init_default():
    """Client should initialize with default values."""
    client = FreeCivClient()

    assert client.reader is None
    assert client.writer is None
    assert client._shutdown_event is None
    assert not client._join_successful.is_set()
    # Handlers are registered in __init__, so should have default handlers
    assert len(client._packet_handlers) == 6  # Default handlers registered
    assert client._packet_reader_task is None
    assert client.game_state is None
    assert client._use_two_byte_type is False
    assert client._packet_debugger is None


@pytest.mark.async_test
async def test_client_init_with_debug_dir():
    """Client should create PacketDebugger when debug_packets_dir provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_dir = os.path.join(tmpdir, "debug")

        client = FreeCivClient(debug_packets_dir=debug_dir)

        assert client._packet_debugger is not None
        assert os.path.exists(debug_dir)


@pytest.mark.async_test
async def test_client_registers_default_handlers():
    """Client should register default packet handlers on init."""
    client = FreeCivClient()

    # Check that default handlers are registered
    assert protocol.PACKET_PROCESSING_STARTED in client._packet_handlers
    assert protocol.PACKET_PROCESSING_FINISHED in client._packet_handlers
    assert protocol.PACKET_SERVER_JOIN_REPLY in client._packet_handlers
    assert protocol.PACKET_SERVER_INFO in client._packet_handlers
    assert protocol.PACKET_CHAT_MSG in client._packet_handlers


# ============================================================================
# register_handler Tests
# ============================================================================


@pytest.mark.async_test
async def test_register_handler_adds_to_dict():
    """register_handler should add handler to _packet_handlers."""
    client = FreeCivClient()

    async def custom_handler(client, game_state, payload):
        pass

    client.register_handler(999, custom_handler)

    assert 999 in client._packet_handlers
    assert client._packet_handlers[999] is custom_handler


@pytest.mark.async_test
async def test_register_handler_overwrites_existing():
    """register_handler should overwrite existing handler for same packet type."""
    client = FreeCivClient()

    async def handler1(client, game_state, payload):
        pass

    async def handler2(client, game_state, payload):
        pass

    client.register_handler(999, handler1)
    client.register_handler(999, handler2)

    # Should have handler2
    assert client._packet_handlers[999] is handler2


# ============================================================================
# connect Tests
# ============================================================================


@pytest.mark.async_test
async def test_connect_success(monkeypatch):
    """connect should establish connection and create game_state."""
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()

    async def mock_open_connection(host, port):
        return mock_reader, mock_writer

    monkeypatch.setattr(asyncio, "open_connection", mock_open_connection)

    client = FreeCivClient()
    result = await client.connect("localhost", 6556)

    assert result is True
    assert client.reader is mock_reader
    assert client.writer is mock_writer
    assert isinstance(client.game_state, GameState)


@pytest.mark.async_test
async def test_connect_failure(monkeypatch):
    """connect should raise exception on connection failure."""
    async def mock_open_connection(host, port):
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr(asyncio, "open_connection", mock_open_connection)

    client = FreeCivClient()

    with pytest.raises(ConnectionRefusedError):
        await client.connect("localhost", 6556)

    # Client state should remain None
    assert client.reader is None
    assert client.writer is None
    assert client.game_state is None


# ============================================================================
# send_join_request Tests
# ============================================================================


@pytest.mark.async_test
async def test_send_join_request_success(mock_stream_pair):
    """send_join_request should encode and send JOIN_REQ packet."""
    mock_reader, mock_writer = mock_stream_pair

    client = FreeCivClient()
    client.reader = mock_reader
    client.writer = mock_writer
    client.game_state = GameState()

    await client.send_join_request("test-user")

    # Should have called write and drain
    assert mock_writer.write.called
    assert mock_writer.drain.called

    # Check that packet was encoded correctly
    written_data = mock_writer.write.call_args[0][0]
    assert len(written_data) > 0  # Should have written something


@pytest.mark.async_test
async def test_send_join_request_not_connected():
    """send_join_request should handle case when not connected."""
    client = FreeCivClient()
    # Don't set reader/writer

    # Should not raise, just return early
    await client.send_join_request("test-user")

    # No exception should occur


@pytest.mark.async_test
async def test_send_join_request_with_debugger(mock_stream_pair):
    """send_join_request should write to packet debugger if enabled."""
    mock_reader, mock_writer = mock_stream_pair

    with tempfile.TemporaryDirectory() as tmpdir:
        debug_dir = os.path.join(tmpdir, "debug")

        client = FreeCivClient(debug_packets_dir=debug_dir)
        client.reader = mock_reader
        client.writer = mock_writer
        client.game_state = GameState()

        await client.send_join_request("test-user")

        # Counter starts at 0 and increments before writing, so first file is outbound_1.packet
        outbound_file = os.path.join(debug_dir, "outbound_1.packet")
        assert os.path.exists(outbound_file)


# ============================================================================
# start_packet_reader Tests
# ============================================================================


@pytest.mark.async_test
async def test_start_packet_reader_creates_task():
    """start_packet_reader should create background task."""
    client = FreeCivClient()
    shutdown_event = asyncio.Event()

    # Mock the reading loop to prevent it from running
    with patch.object(client, '_packet_reading_loop', new_callable=AsyncMock):
        await client.start_packet_reader(shutdown_event)

        assert client._shutdown_event is shutdown_event
        assert client._packet_reader_task is not None
        assert isinstance(client._packet_reader_task, asyncio.Task)

        # Cancel task to clean up
        client._packet_reader_task.cancel()
        try:
            await client._packet_reader_task
        except asyncio.CancelledError:
            pass


# ============================================================================
# _packet_reading_loop Tests
# ============================================================================


@pytest.mark.async_test
async def test_packet_reading_loop_reads_and_dispatches(mock_stream_pair):
    """_packet_reading_loop should read packets and dispatch to handlers."""
    mock_reader, mock_writer = mock_stream_pair

    client = FreeCivClient()
    client.reader = mock_reader
    client.writer = mock_writer
    client.game_state = GameState()
    client._shutdown_event = asyncio.Event()

    # Mock read_packet to return one packet then trigger shutdown
    packet_type = 0  # PROCESSING_STARTED
    payload = b""
    raw_packet = b"\x00\x03\x00"  # Length=3, Type=0

    call_count = 0
    async def mock_read_packet(reader, use_two_byte_type):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return packet_type, payload, raw_packet
        else:
            # Trigger shutdown after first packet
            client._shutdown_event.set()
            await asyncio.sleep(0.1)  # Let loop check event
            return packet_type, payload, raw_packet

    with patch('fc_client.client.protocol.read_packet', side_effect=mock_read_packet):
        # Run loop briefly
        task = asyncio.create_task(client._packet_reading_loop())
        await asyncio.sleep(0.2)

        # Should have read at least one packet
        assert call_count >= 1

        # Cancel task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.async_test
async def test_packet_reading_loop_handles_incomplete_read(mock_stream_pair):
    """_packet_reading_loop should handle IncompleteReadError."""
    mock_reader, mock_writer = mock_stream_pair

    client = FreeCivClient()
    client.reader = mock_reader
    client.writer = mock_writer
    client.game_state = GameState()
    client._shutdown_event = asyncio.Event()

    async def mock_read_packet(reader, use_two_byte_type):
        raise asyncio.IncompleteReadError(b"", 10)

    with patch('fc_client.client.protocol.read_packet', side_effect=mock_read_packet):
        await client._packet_reading_loop()

        # Should have set shutdown event
        assert client._shutdown_event.is_set()


@pytest.mark.async_test
async def test_packet_reading_loop_handles_connection_error(mock_stream_pair):
    """_packet_reading_loop should handle ConnectionError."""
    mock_reader, mock_writer = mock_stream_pair

    client = FreeCivClient()
    client.reader = mock_reader
    client.writer = mock_writer
    client.game_state = GameState()
    client._shutdown_event = asyncio.Event()

    async def mock_read_packet(reader, use_two_byte_type):
        raise ConnectionError("Connection lost")

    with patch('fc_client.client.protocol.read_packet', side_effect=mock_read_packet):
        await client._packet_reading_loop()

        # Should have set shutdown event
        assert client._shutdown_event.is_set()


# ============================================================================
# _dispatch_packet Tests
# ============================================================================


@pytest.mark.async_test
async def test_dispatch_packet_calls_registered_handler():
    """_dispatch_packet should call registered handler."""
    client = FreeCivClient()
    client.game_state = GameState()
    client._shutdown_event = asyncio.Event()

    handler_called = False

    async def mock_handler(client_arg, game_state_arg, payload_arg):
        nonlocal handler_called
        handler_called = True

    client.register_handler(999, mock_handler)

    await client._dispatch_packet(999, b"test")

    assert handler_called is True


@pytest.mark.async_test
async def test_dispatch_packet_calls_unknown_handler():
    """_dispatch_packet should call handle_unknown_packet for unregistered types."""
    client = FreeCivClient()
    client.game_state = GameState()
    client._shutdown_event = asyncio.Event()

    with patch('fc_client.client.handlers.handle_unknown_packet', new_callable=AsyncMock) as mock_unknown:
        await client._dispatch_packet(999, b"test")

        # Should have called unknown packet handler
        mock_unknown.assert_called_once_with(client, client.game_state, 999, b"test")


@pytest.mark.async_test
async def test_dispatch_packet_handles_handler_exception():
    """_dispatch_packet should catch and handle handler exceptions."""
    client = FreeCivClient()
    client.game_state = GameState()
    client._shutdown_event = asyncio.Event()

    async def failing_handler(client_arg, game_state_arg, payload_arg):
        raise ValueError("Handler error")

    client.register_handler(999, failing_handler)

    # Should not raise, should set shutdown
    await client._dispatch_packet(999, b"test")

    # Should have set shutdown event
    assert client._shutdown_event.is_set()


# ============================================================================
# wait_for_join Tests
# ============================================================================


@pytest.mark.async_test
async def test_wait_for_join_success():
    """wait_for_join should return True when join_successful is set."""
    client = FreeCivClient()

    # Set join event in background
    async def set_event():
        await asyncio.sleep(0.1)
        client._join_successful.set()

    asyncio.create_task(set_event())

    result = await client.wait_for_join(timeout=1.0)

    assert result is True


@pytest.mark.async_test
async def test_wait_for_join_timeout():
    """wait_for_join should return False on timeout."""
    client = FreeCivClient()

    # Don't set join event

    result = await client.wait_for_join(timeout=0.1)

    assert result is False


# ============================================================================
# stop_and_disconnect Tests
# ============================================================================


@pytest.mark.async_test
async def test_stop_and_disconnect_cancels_reader_task(mock_stream_pair):
    """stop_and_disconnect should cancel packet reader task."""
    mock_reader, mock_writer = mock_stream_pair

    client = FreeCivClient()
    client.reader = mock_reader
    client.writer = mock_writer
    client.game_state = GameState()

    # Create a running reader task
    async def dummy_reader_loop():
        try:
            while True:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise

    client._packet_reader_task = asyncio.create_task(dummy_reader_loop())

    await client.stop_and_disconnect()

    # Task should be done (cancelled)
    assert client._packet_reader_task.done()


# ============================================================================
# disconnect Tests
# ============================================================================


@pytest.mark.async_test
async def test_disconnect_closes_writer(mock_stream_pair):
    """disconnect should close writer and wait for closure."""
    mock_reader, mock_writer = mock_stream_pair

    client = FreeCivClient()
    client.reader = mock_reader
    client.writer = mock_writer

    result = await client.disconnect()

    assert result is True
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()


@pytest.mark.async_test
async def test_disconnect_clears_delta_cache():
    """disconnect should clear delta cache."""
    client = FreeCivClient()

    # Populate delta cache
    client._delta_cache.update_cache(25, (0,), {"data": "test"})
    assert client._delta_cache.get_cached_packet(25, (0,)) is not None

    await client.disconnect()

    # Cache should be cleared
    assert client._delta_cache.get_cached_packet(25, (0,)) is None


@pytest.mark.async_test
async def test_disconnect_when_not_connected():
    """disconnect should handle case when writer is None."""
    client = FreeCivClient()
    # Don't set writer

    result = await client.disconnect()

    assert result is True  # Should still return True


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.async_test
async def test_client_can_connect_multiple_times(monkeypatch):
    """Client should be able to connect, disconnect, and reconnect."""
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()

    async def mock_open_connection(host, port):
        return AsyncMock(), AsyncMock()

    monkeypatch.setattr(asyncio, "open_connection", mock_open_connection)

    client = FreeCivClient()

    # First connection
    await client.connect("localhost", 6556)
    assert client.reader is not None

    # Disconnect
    await client.disconnect()

    # Second connection
    await client.connect("localhost", 6556)
    assert client.reader is not None


@pytest.mark.async_test
async def test_packet_reading_loop_uses_two_byte_type():
    """_packet_reading_loop should pass use_two_byte_type to read_packet."""
    client = FreeCivClient()
    client.reader = AsyncMock()
    client.writer = AsyncMock()
    client.game_state = GameState()
    client._shutdown_event = asyncio.Event()
    client._use_two_byte_type = True

    call_count = 0
    async def mock_read_packet(reader, use_two_byte_type):
        nonlocal call_count
        call_count += 1
        # Verify use_two_byte_type is passed correctly
        assert use_two_byte_type is True
        client._shutdown_event.set()  # Stop loop
        return 0, b"", b"\x00\x03\x00"

    with patch('fc_client.client.protocol.read_packet', side_effect=mock_read_packet):
        await client._packet_reading_loop()

        assert call_count >= 1
