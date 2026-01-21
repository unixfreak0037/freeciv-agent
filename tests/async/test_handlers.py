"""
Async tests for packet handlers - FreeCiv packet processing functions.

Tests each packet handler to ensure correct payload decoding, state updates,
and event signaling.
"""

import asyncio
from unittest.mock import Mock, patch, AsyncMock
import pytest

from fc_client import handlers, protocol
from fc_client.game_state import GameState, RulesetControl
from fc_client.delta_cache import DeltaCache


# ============================================================================
# Helper Fixtures
# ============================================================================


@pytest.fixture
def mock_client():
    """Create a mock FreeCivClient with necessary attributes."""
    client = Mock()
    client._use_two_byte_type = False
    client._join_successful = asyncio.Event()
    client._shutdown_event = asyncio.Event()
    client._delta_cache = DeltaCache()
    return client


# ============================================================================
# handle_processing_started Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_processing_started_no_errors(mock_client, game_state):
    """handle_processing_started should complete without errors."""
    payload = b""

    # Should not raise
    await handlers.handle_processing_started(mock_client, game_state, payload)

    # No events should be set
    assert not mock_client._join_successful.is_set()
    assert not mock_client._shutdown_event.is_set()


# ============================================================================
# handle_processing_finished Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_processing_finished_no_errors(mock_client, game_state):
    """handle_processing_finished should complete without errors."""
    payload = b""

    # Should not raise
    await handlers.handle_processing_finished(mock_client, game_state, payload)

    # No events should be set
    assert not mock_client._join_successful.is_set()
    assert not mock_client._shutdown_event.is_set()


# ============================================================================
# handle_server_join_reply Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_server_join_reply_success(mock_client, game_state):
    """Successful join should switch protocol version and set join_successful event."""
    payload = b"\x00\x00"  # Dummy payload

    # Mock decode to return success
    with patch('fc_client.handlers.protocol.decode_server_join_reply') as mock_decode:
        mock_decode.return_value = {
            'you_can_join': True,
            'message': 'Welcome!',
            'capability': '+Freeciv-3.0',
            'challenge_file': '',
            'conn_id': 1,
        }

        await handlers.handle_server_join_reply(mock_client, game_state, payload)

    # Should switch to 2-byte packet type
    assert mock_client._use_two_byte_type is True

    # Should set join_successful event
    assert mock_client._join_successful.is_set()

    # Should NOT set shutdown event
    assert not mock_client._shutdown_event.is_set()


@pytest.mark.async_test
async def test_handle_server_join_reply_failure(mock_client, game_state):
    """Failed join should trigger shutdown event."""
    payload = b"\x00\x00"  # Dummy payload

    # Mock decode to return failure
    with patch('fc_client.handlers.protocol.decode_server_join_reply') as mock_decode:
        mock_decode.return_value = {
            'you_can_join': False,
            'message': 'Server full',
            'capability': '+Freeciv-3.0',
            'challenge_file': '',
            'conn_id': 0,
        }

        await handlers.handle_server_join_reply(mock_client, game_state, payload)

    # Should NOT switch to 2-byte packet type
    assert mock_client._use_two_byte_type is False

    # Should NOT set join_successful event
    assert not mock_client._join_successful.is_set()

    # Should set shutdown event
    assert mock_client._shutdown_event.is_set()


@pytest.mark.async_test
async def test_handle_server_join_reply_calls_decode(mock_client, game_state):
    """Handler should call decode_server_join_reply with payload."""
    payload = b"\x01\x02\x03\x04"

    with patch('fc_client.handlers.protocol.decode_server_join_reply') as mock_decode:
        mock_decode.return_value = {
            'you_can_join': True,
            'message': 'OK',
            'capability': '',
            'challenge_file': '',
            'conn_id': 1,
        }

        await handlers.handle_server_join_reply(mock_client, game_state, payload)

        # Verify decode was called with exact payload
        mock_decode.assert_called_once_with(payload)


# ============================================================================
# handle_server_info Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_server_info_updates_game_state(mock_client, game_state):
    """Handler should decode payload and update game_state.server_info."""
    payload = b"\x00" * 100

    server_info_data = {
        'version_label': 'Freeciv 3.0.0',
        'major_version': 3,
        'minor_version': 0,
        'patch_version': 0,
        'emerg_version': 0,
    }

    with patch('fc_client.handlers.protocol.decode_server_info') as mock_decode:
        mock_decode.return_value = server_info_data

        await handlers.handle_server_info(mock_client, game_state, payload)

    # game_state.server_info should be updated
    assert game_state.server_info == server_info_data


@pytest.mark.async_test
async def test_handle_server_info_calls_decode(mock_client, game_state):
    """Handler should call decode_server_info with payload."""
    payload = b"\x01\x02\x03"

    with patch('fc_client.handlers.protocol.decode_server_info') as mock_decode:
        mock_decode.return_value = {
            'version_label': 'Test',
            'major_version': 1,
            'minor_version': 0,
            'patch_version': 0,
            'emerg_version': 0,
        }

        await handlers.handle_server_info(mock_client, game_state, payload)

        # Verify decode was called with exact payload
        mock_decode.assert_called_once_with(payload)


# ============================================================================
# handle_chat_msg Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_chat_msg_uses_delta_protocol(mock_client, game_state):
    """Handler should decode using delta protocol with packet spec."""
    payload = b"\x00" * 50

    chat_data = {
        'message': 'Hello world!',
        'tile': -1,
        'event': 0,
        'turn': 1,
        'phase': 0,
        'conn_id': -1,
    }

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = chat_data

        await handlers.handle_chat_msg(mock_client, game_state, payload)

        # Verify decode_delta_packet was called with correct arguments
        mock_decode.assert_called_once()
        call_args = mock_decode.call_args
        assert call_args[0][0] == payload  # payload
        assert call_args[0][1].packet_type == protocol.PACKET_CHAT_MSG  # packet_spec
        assert call_args[0][2] is mock_client._delta_cache  # delta_cache


@pytest.mark.async_test
async def test_handle_chat_msg_appends_to_history(mock_client, game_state):
    """Handler should append chat message to game_state.chat_history."""
    payload = b"\x00" * 50

    chat_data = {
        'message': 'Test message',
        'tile': 100,
        'event': 5,
        'turn': 42,
        'phase': 1,
        'conn_id': 10,
    }

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = chat_data

        await handlers.handle_chat_msg(mock_client, game_state, payload)

    # Should have one entry in chat_history
    assert len(game_state.chat_history) == 1

    entry = game_state.chat_history[0]
    assert entry['message'] == 'Test message'
    assert entry['tile'] == 100
    assert entry['event'] == 5
    assert entry['turn'] == 42
    assert entry['phase'] == 1
    assert entry['conn_id'] == 10
    assert 'timestamp' in entry  # Should add timestamp


@pytest.mark.async_test
async def test_handle_chat_msg_multiple_messages(mock_client, game_state):
    """Handler should append multiple messages to chat_history."""
    payload = b"\x00" * 50

    messages = [
        {'message': 'msg1', 'tile': -1, 'event': 0, 'turn': 1, 'phase': 0, 'conn_id': 1},
        {'message': 'msg2', 'tile': -1, 'event': 0, 'turn': 2, 'phase': 0, 'conn_id': 2},
        {'message': 'msg3', 'tile': -1, 'event': 0, 'turn': 3, 'phase': 0, 'conn_id': 3},
    ]

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        for msg in messages:
            mock_decode.return_value = msg
            await handlers.handle_chat_msg(mock_client, game_state, payload)

    # Should have all three messages
    assert len(game_state.chat_history) == 3
    assert game_state.chat_history[0]['message'] == 'msg1'
    assert game_state.chat_history[1]['message'] == 'msg2'
    assert game_state.chat_history[2]['message'] == 'msg3'


@pytest.mark.async_test
async def test_handle_chat_msg_adds_timestamp(mock_client, game_state):
    """Handler should add ISO format timestamp to each message."""
    from datetime import datetime
    payload = b"\x00" * 50

    chat_data = {
        'message': 'timestamped',
        'tile': -1,
        'event': 0,
        'turn': 1,
        'phase': 0,
        'conn_id': -1,
    }

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = chat_data

        # Capture timestamp before and after
        before = datetime.now()
        await handlers.handle_chat_msg(mock_client, game_state, payload)
        after = datetime.now()

    entry = game_state.chat_history[0]

    # Should have timestamp field
    assert 'timestamp' in entry

    # Timestamp should be ISO format and parseable
    ts = datetime.fromisoformat(entry['timestamp'])

    # Timestamp should be between before and after
    assert before <= ts <= after


# ============================================================================
# handle_unknown_packet Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_unknown_packet_sets_shutdown(mock_client, game_state):
    """handle_unknown_packet should trigger shutdown event."""
    packet_type = 999
    payload = b"\x01\x02\x03\x04"

    await handlers.handle_unknown_packet(mock_client, game_state, packet_type, payload)

    # Should set shutdown event
    assert mock_client._shutdown_event.is_set()


@pytest.mark.async_test
async def test_handle_unknown_packet_handles_empty_payload(mock_client, game_state):
    """handle_unknown_packet should handle empty payload without error."""
    packet_type = 999
    payload = b""

    # Should not raise
    await handlers.handle_unknown_packet(mock_client, game_state, packet_type, payload)

    # Should still set shutdown
    assert mock_client._shutdown_event.is_set()


@pytest.mark.async_test
async def test_handle_unknown_packet_handles_large_payload(mock_client, game_state):
    """handle_unknown_packet should handle large payloads (only dumps first 64 bytes)."""
    packet_type = 999
    payload = b"\xff" * 1000  # Large payload

    # Should not raise
    await handlers.handle_unknown_packet(mock_client, game_state, packet_type, payload)

    # Should set shutdown
    assert mock_client._shutdown_event.is_set()


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


@pytest.mark.async_test
async def test_handlers_dont_modify_payload(mock_client, game_state):
    """Handlers should not modify the original payload bytes."""
    original_payload = b"\x01\x02\x03\x04"
    payload = bytearray(original_payload)  # Mutable copy

    with patch('fc_client.handlers.protocol.decode_server_join_reply') as mock_decode:
        mock_decode.return_value = {
            'you_can_join': True,
            'message': 'OK',
            'capability': '',
            'challenge_file': '',
            'conn_id': 1,
        }

        await handlers.handle_server_join_reply(mock_client, game_state, payload)

    # Payload should be unchanged
    assert bytes(payload) == original_payload


@pytest.mark.async_test
async def test_handle_chat_msg_with_delta_cache(mock_client, game_state):
    """Handler should work correctly with delta cache populated."""
    payload = b"\x00" * 50

    # Populate delta cache with previous message
    mock_client._delta_cache.update_cache(
        protocol.PACKET_CHAT_MSG,
        (),
        {
            'message': 'old message',
            'tile': 50,
            'event': 1,
            'turn': 10,
            'phase': 0,
            'conn_id': 5,
        }
    )

    new_chat_data = {
        'message': 'new message',
        'tile': 50,  # Same as cache
        'event': 2,  # Changed
        'turn': 11,  # Changed
        'phase': 0,  # Same as cache
        'conn_id': 5,  # Same as cache
    }

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = new_chat_data

        await handlers.handle_chat_msg(mock_client, game_state, payload)

    # Should append new message
    assert len(game_state.chat_history) == 1
    assert game_state.chat_history[0]['message'] == 'new message'


@pytest.mark.async_test
async def test_server_info_replaces_previous_state(mock_client, game_state):
    """handle_server_info should replace previous server_info, not merge."""
    # Set initial server_info
    game_state.server_info = {'old_key': 'old_value'}

    payload = b"\x00" * 100

    new_server_info = {
        'version_label': 'New Version',
        'major_version': 2,
        'minor_version': 0,
        'patch_version': 0,
        'emerg_version': 0,
    }

    with patch('fc_client.handlers.protocol.decode_server_info') as mock_decode:
        mock_decode.return_value = new_server_info

        await handlers.handle_server_info(mock_client, game_state, payload)

    # Should completely replace, not merge
    assert game_state.server_info == new_server_info
    assert 'old_key' not in game_state.server_info


# ============================================================================
# handle_ruleset_control Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_ruleset_control_stores_dataclass(mock_client, game_state):
    """Handler should convert dict to RulesetControl and store in game_state."""
    payload = b"\x00" * 200

    ruleset_data = {
        'num_unit_classes': 10, 'num_unit_types': 50, 'num_impr_types': 40,
        'num_tech_classes': 5, 'num_tech_types': 88, 'num_extra_types': 20,
        'num_tiledef_types': 15, 'num_base_types': 8, 'num_road_types': 6,
        'num_resource_types': 25, 'num_goods_types': 4, 'num_disaster_types': 7,
        'num_achievement_types': 12, 'num_multipliers': 3, 'num_styles': 5,
        'num_music_styles': 3, 'government_count': 8, 'nation_count': 200,
        'num_city_styles': 10, 'terrain_count': 30, 'num_specialist_types': 5,
        'num_normal_specialists': 4, 'num_nation_groups': 15, 'num_nation_sets': 10,
        'preferred_tileset': 'amplio2', 'preferred_soundset': 'stdmusic',
        'preferred_musicset': 'stdmusic', 'popup_tech_help': True,
        'name': 'TestRuleset', 'version': '3.0', 'alt_dir': '',
        'desc_length': 1024, 'num_counters': 5,
    }

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = ruleset_data
        await handlers.handle_ruleset_control(mock_client, game_state, payload)

    # Verify dataclass stored
    assert game_state.ruleset_control is not None
    assert isinstance(game_state.ruleset_control, RulesetControl)
    assert game_state.ruleset_control.name == "TestRuleset"
    assert game_state.ruleset_control.num_unit_types == 50


@pytest.mark.async_test
async def test_handle_ruleset_control_replaces_previous(mock_client, game_state):
    """Handler should completely replace previous ruleset_control."""
    # Set initial
    old_data = {
        'num_unit_classes': 5, 'num_unit_types': 25, 'num_impr_types': 20,
        'num_tech_classes': 3, 'num_tech_types': 44, 'num_extra_types': 10,
        'num_tiledef_types': 8, 'num_base_types': 4, 'num_road_types': 3,
        'num_resource_types': 12, 'num_goods_types': 2, 'num_disaster_types': 3,
        'num_achievement_types': 6, 'num_multipliers': 2, 'num_styles': 3,
        'num_music_styles': 2, 'government_count': 4, 'nation_count': 100,
        'num_city_styles': 5, 'terrain_count': 15, 'num_specialist_types': 3,
        'num_normal_specialists': 2, 'num_nation_groups': 8, 'num_nation_sets': 5,
        'preferred_tileset': 'old', 'preferred_soundset': 'old',
        'preferred_musicset': 'old', 'popup_tech_help': False,
        'name': 'Old', 'version': '1.0', 'alt_dir': '',
        'desc_length': 512, 'num_counters': 2,
    }
    game_state.ruleset_control = RulesetControl(**old_data)

    # Receive new
    payload = b"\x00" * 200
    new_data = {
        'num_unit_classes': 10, 'num_unit_types': 50, 'num_impr_types': 40,
        'num_tech_classes': 5, 'num_tech_types': 88, 'num_extra_types': 20,
        'num_tiledef_types': 15, 'num_base_types': 8, 'num_road_types': 6,
        'num_resource_types': 25, 'num_goods_types': 4, 'num_disaster_types': 7,
        'num_achievement_types': 12, 'num_multipliers': 3, 'num_styles': 5,
        'num_music_styles': 3, 'government_count': 8, 'nation_count': 200,
        'num_city_styles': 10, 'terrain_count': 30, 'num_specialist_types': 5,
        'num_normal_specialists': 4, 'num_nation_groups': 15, 'num_nation_sets': 10,
        'preferred_tileset': 'new', 'preferred_soundset': 'new',
        'preferred_musicset': 'new', 'popup_tech_help': True,
        'name': 'New', 'version': '2.0', 'alt_dir': '',
        'desc_length': 1024, 'num_counters': 5,
    }

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = new_data
        await handlers.handle_ruleset_control(mock_client, game_state, payload)

    # Verify complete replacement
    assert game_state.ruleset_control.name == "New"
    assert game_state.ruleset_control.num_unit_types == 50
