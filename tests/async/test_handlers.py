"""
Async tests for packet handlers - FreeCiv packet processing functions.

Tests each packet handler to ensure correct payload decoding, state updates,
and event signaling.
"""

import asyncio
import struct
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

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = server_info_data

        await handlers.handle_server_info(mock_client, game_state, payload)

    # game_state.server_info should be updated
    assert game_state.server_info == server_info_data


@pytest.mark.async_test
async def test_handle_server_info_calls_decode(mock_client, game_state):
    """Handler should call decode_delta_packet with payload, packet spec, and delta cache."""
    payload = b"\x01\x02\x03"

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = {
            'version_label': 'Test',
            'major_version': 1,
            'minor_version': 0,
            'patch_version': 0,
            'emerg_version': 0,
        }

        await handlers.handle_server_info(mock_client, game_state, payload)

        # Verify decode_delta_packet was called with correct arguments
        mock_decode.assert_called_once()
        call_args = mock_decode.call_args[0]
        assert call_args[0] == payload  # payload
        assert call_args[1].packet_type == protocol.PACKET_SERVER_INFO  # packet_spec
        assert call_args[2] is mock_client._delta_cache  # delta_cache


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

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
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
        'num_base_types': 8, 'num_road_types': 6,
        'num_resource_types': 25, 'num_goods_types': 4, 'num_disaster_types': 7,
        'num_achievement_types': 12, 'num_multipliers': 3, 'num_styles': 5,
        'num_music_styles': 3, 'government_count': 8, 'nation_count': 200,
        'num_city_styles': 10, 'terrain_count': 30, 'num_specialist_types': 5,
        'num_nation_groups': 15, 'num_nation_sets': 10,
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
        'num_base_types': 4, 'num_road_types': 3,
        'num_resource_types': 12, 'num_goods_types': 2, 'num_disaster_types': 3,
        'num_achievement_types': 6, 'num_multipliers': 2, 'num_styles': 3,
        'num_music_styles': 2, 'government_count': 4, 'nation_count': 100,
        'num_city_styles': 5, 'terrain_count': 15, 'num_specialist_types': 3,
        'num_nation_groups': 8, 'num_nation_sets': 5,
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
        'num_base_types': 8, 'num_road_types': 6,
        'num_resource_types': 25, 'num_goods_types': 4, 'num_disaster_types': 7,
        'num_achievement_types': 12, 'num_multipliers': 3, 'num_styles': 5,
        'num_music_styles': 3, 'government_count': 8, 'nation_count': 200,
        'num_city_styles': 10, 'terrain_count': 30, 'num_specialist_types': 5,
        'num_nation_groups': 15, 'num_nation_sets': 10,
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


# ============================================================================
# handle_ruleset_summary Tests
# ============================================================================


@pytest.mark.async_test
async def test_handle_ruleset_summary_stores_text(mock_client, game_state):
    """Handler should decode and store text in game_state.ruleset_summary."""
    payload = b"Test ruleset summary text\x00"

    summary_text = "Test ruleset summary text"

    with patch('fc_client.handlers.protocol.decode_ruleset_summary') as mock_decode:
        mock_decode.return_value = {'text': summary_text}

        await handlers.handle_ruleset_summary(mock_client, game_state, payload)

    # Verify stored in game_state
    assert game_state.ruleset_summary == summary_text


@pytest.mark.async_test
async def test_handle_ruleset_summary_replaces_previous(mock_client, game_state):
    """Handler should replace previous summary, not append."""
    # Set initial summary
    game_state.ruleset_summary = "Old summary text"

    payload = b"New summary text\x00"
    new_text = "New summary text"

    with patch('fc_client.handlers.protocol.decode_ruleset_summary') as mock_decode:
        mock_decode.return_value = {'text': new_text}

        await handlers.handle_ruleset_summary(mock_client, game_state, payload)

    # Should replace, not append
    assert game_state.ruleset_summary == new_text
    assert "Old summary" not in game_state.ruleset_summary


@pytest.mark.async_test
async def test_handle_ruleset_summary_empty(mock_client, game_state):
    """Handler should handle empty string without error."""
    payload = b"\x00"  # Empty string

    with patch('fc_client.handlers.protocol.decode_ruleset_summary') as mock_decode:
        mock_decode.return_value = {'text': ''}

        await handlers.handle_ruleset_summary(mock_client, game_state, payload)

    # Should store empty string (not None)
    assert game_state.ruleset_summary == ""


@pytest.mark.async_test
async def test_handle_ruleset_summary_multiline(mock_client, game_state):
    """Handler should preserve multiline text with newlines."""
    multiline_text = "Line 1\nLine 2\nLine 3"
    payload = b"Line 1\nLine 2\nLine 3\x00"

    with patch('fc_client.handlers.protocol.decode_ruleset_summary') as mock_decode:
        mock_decode.return_value = {'text': multiline_text}

        await handlers.handle_ruleset_summary(mock_client, game_state, payload)

    # Should preserve newlines
    assert game_state.ruleset_summary == multiline_text
    assert "\n" in game_state.ruleset_summary
    assert game_state.ruleset_summary.count("\n") == 2


# ============================================================================
# PACKET_RULESET_DESCRIPTION_PART Handler Tests
# ============================================================================

@pytest.mark.async_test
async def test_handle_ruleset_description_part_single_part(mock_client, game_state):
    """Handler should assemble complete description from single part."""
    text = "This is a complete description."
    payload = b"dummy"

    # Setup ruleset_control with expected length
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=len(text.encode('utf-8')),  # UTF-8 byte length
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': text}

        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should assemble complete description
    assert game_state.ruleset_description == text
    assert game_state.ruleset_description_parts == []  # Accumulator cleared


@pytest.mark.async_test
async def test_handle_ruleset_description_part_multiple_parts(mock_client, game_state):
    """Handler should accumulate and assemble multiple parts correctly."""
    part1 = "This is part one. "
    part2 = "This is part two. "
    part3 = "This is part three."
    expected_total = part1 + part2 + part3
    payload = b"dummy"

    # Setup ruleset_control with expected total length
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=len(expected_total.encode('utf-8')),
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        # Send part 1
        mock_decode.return_value = {'text': part1}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)
        assert game_state.ruleset_description is None  # Not complete yet
        assert len(game_state.ruleset_description_parts) == 1

        # Send part 2
        mock_decode.return_value = {'text': part2}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)
        assert game_state.ruleset_description is None  # Still not complete
        assert len(game_state.ruleset_description_parts) == 2

        # Send part 3 (completes assembly)
        mock_decode.return_value = {'text': part3}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should assemble all parts
    assert game_state.ruleset_description == expected_total
    assert game_state.ruleset_description_parts == []  # Accumulator cleared


@pytest.mark.async_test
async def test_handle_ruleset_description_part_incremental_accumulation(mock_client, game_state):
    """Handler should accumulate parts without assembling until threshold reached."""
    part1 = "Part 1"
    part2 = "Part 2"
    expected_total_length = 100  # Much larger than current accumulation
    payload = b"dummy"

    # Setup ruleset_control with large expected length
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=expected_total_length,
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        # Send part 1
        mock_decode.return_value = {'text': part1}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

        # Should accumulate but not assemble
        assert game_state.ruleset_description is None
        assert game_state.ruleset_description_parts == [part1]

        # Send part 2
        mock_decode.return_value = {'text': part2}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

        # Should accumulate but still not assemble
        assert game_state.ruleset_description is None
        assert game_state.ruleset_description_parts == [part1, part2]


@pytest.mark.async_test
async def test_handle_ruleset_description_part_exact_threshold(mock_client, game_state):
    """Handler should trigger assembly when total bytes exactly matches desc_length."""
    text = "Exactly 20 bytes !!!"  # Note the space for exactly 20 bytes
    assert len(text.encode('utf-8')) == 20
    payload = b"dummy"

    # Setup with exact expected length
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=20,  # Exact match
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': text}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should trigger assembly at exact threshold
    assert game_state.ruleset_description == text
    assert game_state.ruleset_description_parts == []


@pytest.mark.async_test
async def test_handle_ruleset_description_part_missing_ruleset_control(mock_client, game_state):
    """Handler should handle missing RULESET_CONTROL gracefully with warning."""
    text = "Some description text"
    payload = b"dummy"

    # No ruleset_control set (None)
    assert game_state.ruleset_control is None

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': text}

        # Should not crash, just warn and accumulate
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should still accumulate part
    assert game_state.ruleset_description_parts == [text]
    # Should not assemble (no expected length)
    assert game_state.ruleset_description is None


@pytest.mark.async_test
async def test_handle_ruleset_description_part_empty_string(mock_client, game_state):
    """Handler should handle empty string chunks correctly."""
    text = ""
    payload = b"dummy"

    # Setup with zero expected length
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=0,  # Zero length expected
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': text}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should assemble immediately (0 >= 0)
    assert game_state.ruleset_description == ""
    assert game_state.ruleset_description_parts == []


@pytest.mark.async_test
async def test_handle_ruleset_description_part_unicode_text(mock_client, game_state):
    """Handler should handle Unicode multi-byte characters correctly."""
    text = "Hello 世界! 🌍"  # Multi-byte UTF-8 characters
    payload = b"dummy"

    # Setup with UTF-8 byte length (not character count!)
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=len(text.encode('utf-8')),  # UTF-8 bytes, not character count
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': text}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should assemble correctly with Unicode
    assert game_state.ruleset_description == text
    assert game_state.ruleset_description_parts == []


@pytest.mark.async_test
async def test_handle_ruleset_description_part_multiline_text(mock_client, game_state):
    """Handler should preserve newlines in multiline text."""
    text = "Line 1\nLine 2\nLine 3"
    payload = b"dummy"

    # Setup with expected length
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=len(text.encode('utf-8')),
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': text}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should preserve newlines
    assert game_state.ruleset_description == text
    assert "\n" in game_state.ruleset_description
    assert game_state.ruleset_description.count("\n") == 2


@pytest.mark.async_test
async def test_handle_ruleset_description_part_exceeds_expected_length(mock_client, game_state):
    """Handler should assemble even if parts exceed expected desc_length."""
    part1 = "Part 1 text"
    part2 = "Part 2 text"
    expected_total = part1 + part2
    # Set expected length slightly less than actual total
    expected_length = len(part1.encode('utf-8')) + 5  # Will be exceeded by part2
    payload = b"dummy"

    # Setup ruleset_control
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=expected_length,
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        # Send part 1
        mock_decode.return_value = {'text': part1}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)
        assert game_state.ruleset_description is None  # Not yet

        # Send part 2 (exceeds expected length)
        mock_decode.return_value = {'text': part2}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should assemble when threshold is exceeded (using >=)
    assert game_state.ruleset_description == expected_total
    assert game_state.ruleset_description_parts == []


@pytest.mark.async_test
async def test_handle_ruleset_description_part_replaces_previous(mock_client, game_state):
    """Handler should replace previous description when new one is assembled."""
    old_desc = "Old description"
    new_desc = "New description"
    payload = b"dummy"

    # Set old description
    game_state.ruleset_description = old_desc

    # Setup ruleset_control for new description
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=len(new_desc.encode('utf-8')),
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': new_desc}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should replace old with new
    assert game_state.ruleset_description == new_desc
    assert game_state.ruleset_description != old_desc


@pytest.mark.async_test
async def test_handle_ruleset_description_part_calls_decode(mock_client, game_state):
    """Handler should call decode_ruleset_description_part with payload."""
    text = "Test description"
    payload = b"test_payload_data"

    # Setup ruleset_control
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=len(text.encode('utf-8')),
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        mock_decode.return_value = {'text': text}

        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

        # Verify decoder was called with payload
        mock_decode.assert_called_once_with(payload)


@pytest.mark.async_test
async def test_handle_ruleset_description_part_byte_calculation_accuracy(mock_client, game_state):
    """Handler should count UTF-8 bytes accurately, not characters."""
    # String with multi-byte characters
    part1 = "Hello"  # 5 bytes ASCII
    part2 = " 世界"   # 1 space (1 byte) + 2 Chinese chars (6 bytes) = 7 bytes
    # Total: 5 + 7 = 12 bytes, but only 8 characters
    expected_bytes = len((part1 + part2).encode('utf-8'))
    assert expected_bytes == 12  # Verify our calculation
    payload = b"dummy"

    # Setup with byte length (not character count)
    from fc_client.game_state import RulesetControl
    game_state.ruleset_control = RulesetControl(
        num_unit_classes=0, num_unit_types=0, num_impr_types=0,
        num_tech_classes=0, num_tech_types=0, num_extra_types=0,
        num_base_types=0, num_road_types=0,
        num_resource_types=0, num_goods_types=0, num_disaster_types=0,
        num_achievement_types=0, num_multipliers=0, num_styles=0,
        num_music_styles=0, government_count=0, nation_count=0,
        num_city_styles=0, terrain_count=0, num_specialist_types=0,
        num_nation_groups=0, num_nation_sets=0,
        preferred_tileset="", preferred_soundset="", preferred_musicset="",
        popup_tech_help=False, name="test", version="1.0", alt_dir="",
        desc_length=expected_bytes,  # 12 bytes, not 8 characters
        num_counters=0
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_description_part') as mock_decode:
        # Send part 1 (5 bytes)
        mock_decode.return_value = {'text': part1}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)
        assert game_state.ruleset_description is None  # Not complete (5 < 12)

        # Send part 2 (7 bytes, total 12)
        mock_decode.return_value = {'text': part2}
        await handlers.handle_ruleset_description_part(mock_client, game_state, payload)

    # Should assemble when byte count (not char count) reaches threshold
    assert game_state.ruleset_description == part1 + part2
    assert len(game_state.ruleset_description) == 8  # 8 characters
    assert len(game_state.ruleset_description.encode('utf-8')) == 12  # 12 bytes


@pytest.mark.async_test
async def test_handle_ruleset_control_resets_accumulator(mock_client, game_state):
    """Handler should reset description accumulator when RULESET_CONTROL received."""
    # Setup: Pre-fill accumulator with stale data
    game_state.ruleset_description_parts = ["stale part 1", "stale part 2"]
    game_state.ruleset_description = "stale complete description"

    # Create sample RULESET_CONTROL packet data
    from fc_client.game_state import RulesetControl
    ruleset_data = {
        'num_unit_classes': 5, 'num_unit_types': 10, 'num_impr_types': 15,
        'num_tech_classes': 3, 'num_tech_types': 20, 'num_extra_types': 8,
        'num_base_types': 6, 'num_road_types': 7,
        'num_resource_types': 12, 'num_goods_types': 3, 'num_disaster_types': 5,
        'num_achievement_types': 10, 'num_multipliers': 4, 'num_styles': 3,
        'num_music_styles': 2, 'government_count': 8, 'nation_count': 50,
        'num_city_styles': 5, 'terrain_count': 15, 'num_specialist_types': 4,
        'num_nation_groups': 10, 'num_nation_sets': 5,
        'preferred_tileset': "amplio2", 'preferred_soundset': "stdsounds",
        'preferred_musicset': "stdmusic", 'popup_tech_help': True,
        'name': "Civ2Civ3", 'version': "3.3", 'alt_dir': "",
        'desc_length': 1000, 'num_counters': 2
    }
    payload = b"dummy"

    with patch('fc_client.handlers.protocol.decode_delta_packet') as mock_decode:
        mock_decode.return_value = ruleset_data

        await handlers.handle_ruleset_control(mock_client, game_state, payload)

    # Should reset accumulator
    assert game_state.ruleset_description_parts == []
    assert game_state.ruleset_description is None
    # Should store new ruleset_control
    assert game_state.ruleset_control is not None
    assert game_state.ruleset_control.name == "Civ2Civ3"


# PACKET_RULESET_NATION_SETS Tests

async def test_handle_ruleset_nation_sets_stores_in_game_state(mock_client, game_state):
    """Test handler stores nation sets in game state."""
    from fc_client.game_state import NationSet

    # Delta protocol format with bitvector and null-terminated strings
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x02'  # nsets=2
        # names[2] - null-terminated variable-length strings
        b'Core\x00'
        b'Extended\x00'
        # rule_names[2]
        b'core\x00'
        b'extended\x00'
        # descriptions[2]
        b'Default nations\x00'
        b'Additional nations\x00'
    )

    await handlers.handle_ruleset_nation_sets(mock_client, game_state, payload)

    assert len(game_state.nation_sets) == 2
    assert game_state.nation_sets[0].name == 'Core'
    assert game_state.nation_sets[0].rule_name == 'core'
    assert game_state.nation_sets[0].description == 'Default nations'
    assert game_state.nation_sets[1].name == 'Extended'


async def test_handle_ruleset_nation_sets_replaces_previous(mock_client, game_state):
    """Test handler replaces previous nation sets data."""
    from fc_client.game_state import NationSet

    game_state.nation_sets = [NationSet('Old', 'old', 'Old data')]

    # Delta protocol format with bitvector and null-terminated strings
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x01'  # nsets=1
        # Null-terminated variable-length strings
        b'Core\x00'  # names[0]
        b'core\x00'  # rule_names[0]
        b'New data\x00'  # descriptions[0]
    )

    await handlers.handle_ruleset_nation_sets(mock_client, game_state, payload)

    assert len(game_state.nation_sets) == 1
    assert game_state.nation_sets[0].name == 'Core'


async def test_handle_ruleset_nation_sets_empty_list(mock_client, game_state):
    """Test handler handles nsets=0 correctly."""
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x00'  # nsets=0
    )

    await handlers.handle_ruleset_nation_sets(mock_client, game_state, payload)

    assert game_state.nation_sets == []


async def test_handle_ruleset_nation_sets_calls_decoder(mock_client, game_state):
    """Test handler calls decoder function."""
    # Delta protocol format with bitvector and null-terminated strings
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x01'  # nsets=1
        # Null-terminated variable-length strings
        b'Core\x00'  # names[0]
        b'core\x00'  # rule_names[0]
        b'Description\x00'  # descriptions[0]
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_nation_sets') as mock_decode:
        mock_decode.return_value = {
            'nsets': 1,
            'names': ['Core'],
            'rule_names': ['core'],
            'descriptions': ['Description']
        }

        await handlers.handle_ruleset_nation_sets(mock_client, game_state, payload)

        mock_decode.assert_called_once_with(payload)


# ============================================================================
# PACKET_RULESET_NATION_GROUPS Handler Tests
# ============================================================================

async def test_handle_ruleset_nation_groups_stores_in_game_state(mock_client, game_state):
    """Test handler stores nation groups in game state."""
    from fc_client.game_state import NationGroup

    # Delta protocol format with bitvector and null-terminated strings
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x03'  # ngroups=3
        # groups[3] - null-terminated variable-length strings
        b'?nationgroup:Ancient\x00'
        b'?nationgroup:Medieval\x00'
        b'?nationgroup:Modern\x00'
        # hidden[3] - boolean values (1 byte each)
        b'\x00'  # hidden[0]=false (visible)
        b'\x00'  # hidden[1]=false (visible)
        b'\x01'  # hidden[2]=true (hidden)
    )

    await handlers.handle_ruleset_nation_groups(mock_client, game_state, payload)

    assert len(game_state.nation_groups) == 3
    assert game_state.nation_groups[0].name == '?nationgroup:Ancient'
    assert game_state.nation_groups[0].hidden == False
    assert game_state.nation_groups[1].name == '?nationgroup:Medieval'
    assert game_state.nation_groups[1].hidden == False
    assert game_state.nation_groups[2].name == '?nationgroup:Modern'
    assert game_state.nation_groups[2].hidden == True


async def test_handle_ruleset_nation_groups_replaces_previous(mock_client, game_state):
    """Test handler replaces previous nation groups data."""
    from fc_client.game_state import NationGroup

    game_state.nation_groups = [NationGroup('Old', False)]

    # Delta protocol format with bitvector and null-terminated strings
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x01'  # ngroups=1
        # Null-terminated variable-length strings
        b'?nationgroup:Ancient\x00'  # groups[0]
        b'\x00'  # hidden[0]=false
    )

    await handlers.handle_ruleset_nation_groups(mock_client, game_state, payload)

    assert len(game_state.nation_groups) == 1
    assert game_state.nation_groups[0].name == '?nationgroup:Ancient'


async def test_handle_ruleset_nation_groups_empty_list(mock_client, game_state):
    """Test handler handles ngroups=0 correctly."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x00'  # ngroups=0
    )

    await handlers.handle_ruleset_nation_groups(mock_client, game_state, payload)

    assert game_state.nation_groups == []


async def test_handle_ruleset_nation_groups_calls_decoder(mock_client, game_state):
    """Test handler calls decoder function."""
    # Delta protocol format with bitvector and null-terminated strings
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x01'  # ngroups=1
        # Null-terminated variable-length strings
        b'Ancient\x00'  # groups[0]
        b'\x00'  # hidden[0]=false
    )

    with patch('fc_client.handlers.protocol.decode_ruleset_nation_groups') as mock_decode:
        mock_decode.return_value = {
            'ngroups': 1,
            'groups': ['Ancient'],
            'hidden': [False]
        }

        await handlers.handle_ruleset_nation_groups(mock_client, game_state, payload)

        mock_decode.assert_called_once_with(payload)


async def test_handle_ruleset_nation_groups_transforms_parallel_arrays(mock_client, game_state):
    """Test handler correctly transforms parallel arrays into objects."""
    from fc_client.game_state import NationGroup

    # Delta protocol format with bitvector and null-terminated strings
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x04'  # ngroups=4
        b'Ancient\x00'
        b'Medieval\x00'
        b'Modern\x00'
        b'Barbarian\x00'
        b'\x00'  # hidden[0]=false
        b'\x00'  # hidden[1]=false
        b'\x00'  # hidden[2]=false
        b'\x01'  # hidden[3]=true
    )

    await handlers.handle_ruleset_nation_groups(mock_client, game_state, payload)

    # Verify transformation from parallel arrays to objects
    assert len(game_state.nation_groups) == 4
    assert all(isinstance(group, NationGroup) for group in game_state.nation_groups)

    # Verify each group has correct name and hidden status
    assert game_state.nation_groups[0].name == 'Ancient'
    assert game_state.nation_groups[0].hidden == False
    assert game_state.nation_groups[1].name == 'Medieval'
    assert game_state.nation_groups[1].hidden == False
    assert game_state.nation_groups[2].name == 'Modern'
    assert game_state.nation_groups[2].hidden == False
    assert game_state.nation_groups[3].name == 'Barbarian'
    assert game_state.nation_groups[3].hidden == True


# ============================================================================
# PACKET_NATION_AVAILABILITY Tests (3 tests) - Delta Protocol
# ============================================================================


@pytest.mark.async_test
async def test_handle_nation_availability_basic(mock_client, game_state):
    """Test handler updates game state with nation availability data (delta protocol)."""
    # Delta protocol packet with 3 nations
    payload = (
        b'\x03'      # bitvector: bits 0,1 set (ncount and is_pickable present), bit 2 clear
        b'\x00\x03'  # ncount=3 (UINT16, big-endian)
        b'\x01'      # is_pickable[0]=True
        b'\x00'      # is_pickable[1]=False
        b'\x01'      # is_pickable[2]=True
    )

    await handlers.handle_nation_availability(mock_client, game_state, payload)

    # Verify game state was updated
    assert game_state.nation_availability is not None
    assert game_state.nation_availability['ncount'] == 3
    assert game_state.nation_availability['is_pickable'] == [True, False, True]
    assert game_state.nation_availability['nationset_change'] is False


@pytest.mark.async_test
async def test_handle_nation_availability_nationset_change(mock_client, game_state):
    """Test handler correctly detects nationset_change flag via boolean header folding."""
    # Delta protocol packet with nationset_change=True (folded in bitvector bit 2)
    payload = (
        b'\x07'      # bitvector: bits 0,1,2 set (nationset_change=True via folding)
        b'\x00\x02'  # ncount=2 (UINT16, big-endian)
        b'\x01'      # is_pickable[0]=True
        b'\x01'      # is_pickable[1]=True
    )

    await handlers.handle_nation_availability(mock_client, game_state, payload)

    # Verify nationset_change flag is detected from bitvector
    assert game_state.nation_availability is not None
    assert game_state.nation_availability['nationset_change'] is True
    assert game_state.nation_availability['ncount'] == 2
    assert game_state.nation_availability['is_pickable'] == [True, True]


@pytest.mark.async_test
async def test_handle_nation_availability_with_nations_loaded(mock_client, game_state):
    """Test handler cross-references with loaded nation data."""
    from fc_client.game_state import Nation

    # Pre-populate game state with nation data
    nation0 = Nation(
        id=0, translation_domain='', adjective='Roman', rule_name='roman',
        noun_plural='Romans', graphic_str='', graphic_alt='', legend='',
        style=0, leader_count=1, leader_name=['Caesar'], leader_is_male=[True],
        is_playable=True, barbarian_type=0, nsets=0, sets=[], ngroups=0, groups=[],
        init_government_id=-1, init_techs_count=0, init_techs=[],
        init_units_count=0, init_units=[], init_buildings_count=0, init_buildings=[]
    )
    nation1 = Nation(
        id=1, translation_domain='', adjective='Babylonian', rule_name='babylonian',
        noun_plural='Babylonians', graphic_str='', graphic_alt='', legend='',
        style=0, leader_count=1, leader_name=['Hammurabi'], leader_is_male=[True],
        is_playable=True, barbarian_type=0, nsets=0, sets=[], ngroups=0, groups=[],
        init_government_id=-1, init_techs_count=0, init_techs=[],
        init_units_count=0, init_units=[], init_buildings_count=0, init_buildings=[]
    )

    game_state.nations = {0: nation0, 1: nation1}

    # Delta protocol packet indicating only nation 0 is available
    payload = (
        b'\x03'      # bitvector: bits 0,1 set, bit 2 clear (nationset_change=False)
        b'\x00\x02'  # ncount=2 (UINT16, big-endian)
        b'\x01'      # is_pickable[0]=True
        b'\x00'      # is_pickable[1]=False
    )

    await handlers.handle_nation_availability(mock_client, game_state, payload)

    # Verify game state was updated correctly
    assert game_state.nation_availability is not None
    assert game_state.nation_availability['ncount'] == 2
    assert game_state.nation_availability['is_pickable'] == [True, False]

    # Handler should successfully cross-reference with nation data
    # (We can't directly test console output, but we verify no exceptions occur)
    # and the availability data matches the nation IDs we have


async def test_handle_ruleset_game(mock_client, game_state):
    """Test handle_ruleset_game with complete game configuration."""
    # Build payload with actual observed structure
    # 4 unknown bytes
    payload = struct.pack('<BBBB', 248, 63, 1, 23)

    # 3 veteran levels
    payload += struct.pack('<B', 3)  # veteran_levels

    # Veteran names
    payload += b'Green\x00'
    payload += b'Veteran\x00'
    payload += b'Hardened\x00'

    # Power factors
    payload += struct.pack('>H', 100)
    payload += struct.pack('>H', 150)
    payload += struct.pack('>H', 175)

    # Move bonuses
    payload += struct.pack('>I', 0)
    payload += struct.pack('>I', 3)
    payload += struct.pack('>I', 6)

    # Base raise chances
    payload += struct.pack('<B', 50)
    payload += struct.pack('<B', 33)
    payload += struct.pack('<B', 20)

    # Work raise chances
    payload += struct.pack('<B', 0)
    payload += struct.pack('<B', 5)
    payload += struct.pack('<B', 10)

    # Background color (RGB)
    payload += struct.pack('<BBB', 139, 140, 141)

    # Call handler
    await handlers.handle_ruleset_game(mock_client, game_state, payload)

    # Verify game state was updated
    assert game_state.ruleset_game is not None
    # Tech/building fields not in actual packet (defaults)
    assert game_state.ruleset_game.default_specialist == 0
    assert game_state.ruleset_game.global_init_techs_count == 0
    assert game_state.ruleset_game.global_init_techs == []
    assert game_state.ruleset_game.global_init_buildings_count == 0
    assert game_state.ruleset_game.global_init_buildings == []
    assert game_state.ruleset_game.veteran_levels == 3
    assert game_state.ruleset_game.veteran_name == ['Green', 'Veteran', 'Hardened']
    assert game_state.ruleset_game.power_fact == [100, 150, 175]
    assert game_state.ruleset_game.move_bonus == [0, 3, 6]
    assert game_state.ruleset_game.base_raise_chance == [50, 33, 20]
    assert game_state.ruleset_game.work_raise_chance == [0, 5, 10]
    assert game_state.ruleset_game.background_red == 139
    assert game_state.ruleset_game.background_green == 140
    assert game_state.ruleset_game.background_blue == 141


@pytest.mark.asyncio
async def test_handle_ruleset_achievement(mock_client, game_state):
    """Test RULESET_ACHIEVEMENT handler stores achievement correctly."""
    # Real captured packet data
    payload = bytes([
        0x26,  # id = 38
        # name = "Spaceship Launch"
        0x53, 0x70, 0x61, 0x63, 0x65, 0x73, 0x68, 0x69, 0x70, 0x20,
        0x4c, 0x61, 0x75, 0x6e, 0x63, 0x68, 0x00,
        # rule_name = "Spaceship Launch"
        0x53, 0x70, 0x61, 0x63, 0x65, 0x73, 0x68, 0x69, 0x70, 0x20,
        0x4c, 0x61, 0x75, 0x6e, 0x63, 0x68, 0x00,
        0x00,  # type = 0 (ACHIEVEMENT_SPACESHIP)
        0x01   # unique = True
    ])

    await handlers.handle_ruleset_achievement(mock_client, game_state, payload)

    # Verify storage
    assert 38 in game_state.achievements
    achievement = game_state.achievements[38]
    assert achievement.name == "Spaceship Launch"
    assert achievement.rule_name == "Spaceship Launch"
    assert achievement.type == 0
    assert achievement.unique is True


async def test_handle_ruleset_trade(mock_client, game_state):
    """Test handle_ruleset_trade processes packet correctly."""
    # Delta protocol: bitvector=0x0E (bits 1,2,3), trade_pct=100, cancelling=0, bonus_type=1
    payload = bytes([0x0E, 0, 100, 0, 1])  # bitvector, pct (big-endian), cancel, bonus

    await handlers.handle_ruleset_trade(mock_client, game_state, payload)

    assert 0 in game_state.trade_routes
    trade = game_state.trade_routes[0]
    assert trade.id == 0  # Not in payload, defaults to 0
    assert trade.trade_pct == 100
    assert trade.cancelling == 0
    assert trade.bonus_type == 1
