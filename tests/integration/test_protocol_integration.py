"""
Integration tests for fc_client/protocol.py

Tests complete packet processing pipelines with delta protocol and cache integration.
"""

import struct
import pytest

from fc_client.protocol import (
    decode_delta_packet,
    decode_server_join_reply,
    decode_server_info,
    encode_string,
    encode_bool,
    encode_uint32,
    encode_sint16,
    read_bitvector,
    is_bit_set,
)
from fc_client.packet_specs import PacketSpec, FieldSpec, PACKET_SPECS

# ============================================================================
# Helper Functions
# ============================================================================


def create_test_packet_spec(packet_type: int, fields: list) -> PacketSpec:
    """
    Create a test PacketSpec for integration testing.

    Args:
        packet_type: Numeric packet type
        fields: List of dicts with field specifications

    Returns:
        PacketSpec instance
    """
    field_specs = [FieldSpec(**f) for f in fields]
    return PacketSpec(
        packet_type=packet_type,
        name=f"TEST_PACKET_{packet_type}",
        has_delta=True,
        fields=field_specs,
    )


def build_sint16_bytes(value: int) -> bytes:
    """Helper to build big-endian SINT16 bytes."""
    return struct.pack(">h", value)


def build_sint32_bytes(value: int) -> bytes:
    """Helper to build big-endian SINT32 bytes."""
    return struct.pack(">i", value)


# ============================================================================
# Phase 5: Delta Protocol Integration
# ============================================================================


# Cache behavior tests (8 tests)


@pytest.mark.integration
def test_delta_packet_first_packet_no_cache(delta_cache):
    """Test decoding first packet with empty cache (all fields in payload)."""
    # Create simple test spec with one key field and two non-key fields
    spec = create_test_packet_spec(
        packet_type=100,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "name", "type_name": "STRING"},
            {"name": "value", "type_name": "SINT32"},
        ],
    )

    # Build payload: bitvector + key field + all non-key fields
    # IMPORTANT: Delta protocol transmits bitvector BEFORE key fields
    # Bitvector: 2 bits = 1 byte, bits 0 and 1 set = 0b00000011 = 0x03
    payload = (
        b"\x03"  # bitvector: bits 0,1 set (comes FIRST)
        + encode_uint32(42)  # id (key field, comes SECOND)
        + encode_string("test")  # name
        + build_sint32_bytes(999)  # value
    )

    result = decode_delta_packet(payload, spec, delta_cache)

    assert result["id"] == 42
    assert result["name"] == "test"
    assert result["value"] == 999

    # Verify cache was updated (includes key fields)
    cached = delta_cache.get_cached_packet(100, (42,))
    assert cached == {"id": 42, "name": "test", "value": 999}


@pytest.mark.integration
def test_delta_packet_second_packet_no_changes(delta_cache):
    """Test decoding second packet with bitvector all zeros (use cache)."""
    spec = create_test_packet_spec(
        packet_type=100,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "name", "type_name": "STRING"},
            {"name": "value", "type_name": "SINT32"},
        ],
    )

    # First packet: populate cache
    payload1 = (
        b"\x03"  # bits 0,1 set
        + encode_uint32(42)
        + encode_string("test")
        + build_sint32_bytes(999)
    )
    result1 = decode_delta_packet(payload1, spec, delta_cache)

    # Second packet: no changes (bitvector all zeros)
    payload2 = b"\x00" + encode_uint32(42)  # bitvector: no bits set, use cache  # Same id
    result2 = decode_delta_packet(payload2, spec, delta_cache)

    # Should get cached values
    assert result2["id"] == 42
    assert result2["name"] == "test"  # From cache
    assert result2["value"] == 999  # From cache


@pytest.mark.integration
def test_delta_packet_second_packet_partial_changes(delta_cache):
    """Test mixed cache/payload with some fields changed."""
    spec = create_test_packet_spec(
        packet_type=100,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "name", "type_name": "STRING"},
            {"name": "value", "type_name": "SINT32"},
            {"name": "count", "type_name": "SINT16"},
        ],
    )

    # First packet: populate cache
    payload1 = (
        b"\x07"  # bits 0,1,2 set (3 non-key fields)
        + encode_uint32(42)
        + encode_string("alice")
        + build_sint32_bytes(100)
        + build_sint16_bytes(5)
    )
    result1 = decode_delta_packet(payload1, spec, delta_cache)

    # Second packet: only change 'value' (bit 1)
    payload2 = (
        b"\x02"  # Only bit 1 set (value changed)
        + encode_uint32(42)
        + build_sint32_bytes(200)  # New value
    )
    result2 = decode_delta_packet(payload2, spec, delta_cache)

    # Should have cached name and count, new value
    assert result2["id"] == 42
    assert result2["name"] == "alice"  # From cache
    assert result2["value"] == 200  # New value
    assert result2["count"] == 5  # From cache


@pytest.mark.integration
def test_delta_packet_bitvector_boundary(delta_cache):
    """Test bitvector handling at byte boundaries (8 vs 9 fields)."""
    # 8 non-key fields = 1 byte bitvector
    spec_8fields = create_test_packet_spec(
        packet_type=101,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "f1", "type_name": "SINT16"},
            {"name": "f2", "type_name": "SINT16"},
            {"name": "f3", "type_name": "SINT16"},
            {"name": "f4", "type_name": "SINT16"},
            {"name": "f5", "type_name": "SINT16"},
            {"name": "f6", "type_name": "SINT16"},
            {"name": "f7", "type_name": "SINT16"},
            {"name": "f8", "type_name": "SINT16"},
        ],
    )

    # All 8 bits set = 0xFF
    payload = (
        b"\xff"  # 1 byte bitvector, all bits set
        + encode_uint32(1)
        + build_sint16_bytes(1)
        + build_sint16_bytes(2)
        + build_sint16_bytes(3)
        + build_sint16_bytes(4)
        + build_sint16_bytes(5)
        + build_sint16_bytes(6)
        + build_sint16_bytes(7)
        + build_sint16_bytes(8)
    )

    result = decode_delta_packet(payload, spec_8fields, delta_cache)
    assert result["f8"] == 8

    # 9 non-key fields = 2 byte bitvector
    spec_9fields = create_test_packet_spec(
        packet_type=102,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "f1", "type_name": "SINT16"},
            {"name": "f2", "type_name": "SINT16"},
            {"name": "f3", "type_name": "SINT16"},
            {"name": "f4", "type_name": "SINT16"},
            {"name": "f5", "type_name": "SINT16"},
            {"name": "f6", "type_name": "SINT16"},
            {"name": "f7", "type_name": "SINT16"},
            {"name": "f8", "type_name": "SINT16"},
            {"name": "f9", "type_name": "SINT16"},
        ],
    )

    # 9 bits = 2 bytes, bits 0-8 set
    # Note: bitvectors use little-endian byte order
    # Bits 0-7 in first byte (\xff), bit 8 in second byte (\x01)
    payload = (
        b"\xff\x01"  # 2 byte bitvector, 9 bits set (little-endian)
        + encode_uint32(1)
        + build_sint16_bytes(1)
        + build_sint16_bytes(2)
        + build_sint16_bytes(3)
        + build_sint16_bytes(4)
        + build_sint16_bytes(5)
        + build_sint16_bytes(6)
        + build_sint16_bytes(7)
        + build_sint16_bytes(8)
        + build_sint16_bytes(9)
    )

    result = decode_delta_packet(payload, spec_9fields, delta_cache)
    assert result["f9"] == 9


@pytest.mark.integration
def test_delta_packet_key_field_always_transmitted(delta_cache):
    """Test that key field is always transmitted (not in bitvector)."""
    spec = create_test_packet_spec(
        packet_type=103,
        fields=[
            {"name": "server_id", "type_name": "UINT32", "is_key": True},
            {"name": "turn", "type_name": "SINT16"},
        ],
    )

    # Packet with bitvector and key field
    payload = (
        b"\x01"  # Bitvector for non-key field
        + encode_uint32(99)  # Key field always present (after bitvector)
        + build_sint16_bytes(42)
    )

    result = decode_delta_packet(payload, spec, delta_cache)
    assert result["server_id"] == 99  # Key field
    assert result["turn"] == 42


@pytest.mark.integration
def test_delta_packet_bool_header_folding(delta_cache):
    """Test BOOL fields use bitvector bit value (no separate byte)."""
    spec = create_test_packet_spec(
        packet_type=104,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "is_active", "type_name": "BOOL"},
            {"name": "count", "type_name": "SINT16"},
        ],
    )

    # Bitvector: bit 0 (is_active) = True, bit 1 (count) = True
    # 0b00000011 = 0x03
    payload = (
        b"\x03"  # Both bits set
        + encode_uint32(1)
        +
        # No byte for is_active (header folding)
        build_sint16_bytes(10)  # Only count has payload byte
    )

    result = decode_delta_packet(payload, spec, delta_cache)
    assert result["is_active"] is True  # From bitvector bit
    assert result["count"] == 10


@pytest.mark.integration
def test_delta_packet_cache_update(delta_cache):
    """Test that cache is properly updated after decoding."""
    spec = create_test_packet_spec(
        packet_type=105,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "data", "type_name": "STRING"},
        ],
    )

    payload = b"\x01" + encode_uint32(7) + encode_string("cached_value")

    decode_delta_packet(payload, spec, delta_cache)

    # Verify cache contents
    cached = delta_cache.get_cached_packet(105, (7,))
    assert cached is not None
    assert cached["data"] == "cached_value"


@pytest.mark.integration
def test_delta_packet_multiple_keys(delta_cache):
    """Test packets with multiple key fields (composite key)."""
    spec = create_test_packet_spec(
        packet_type=106,
        fields=[
            {"name": "player_id", "type_name": "UINT32", "is_key": True},
            {"name": "city_id", "type_name": "UINT32", "is_key": True},
            {"name": "population", "type_name": "SINT32"},
        ],
    )

    payload = (
        b"\x01"  # bitvector (comes first)
        + encode_uint32(10)  # player_id (key 1)
        + encode_uint32(20)  # city_id (key 2)
        + build_sint32_bytes(5000)
    )

    result = decode_delta_packet(payload, spec, delta_cache)

    # Verify composite key caching
    cached = delta_cache.get_cached_packet(106, (10, 20))
    assert cached is not None
    assert cached["population"] == 5000


# End-to-end tests (7 tests)


@pytest.mark.integration
def test_delta_packet_all_field_types(delta_cache):
    """Test delta packet with all supported field types."""
    spec = create_test_packet_spec(
        packet_type=107,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "name", "type_name": "STRING"},
            {"name": "score", "type_name": "SINT32"},
            {"name": "level", "type_name": "SINT16"},
            {"name": "gold", "type_name": "UINT32"},
            {"name": "is_alive", "type_name": "BOOL"},
        ],
    )

    # All non-key fields present (bits 0-4 set = 0x1F)
    payload = (
        b"\x1f"  # 5 bits set (excluding BOOL byte)
        + encode_uint32(1)
        + encode_string("player1")
        + build_sint32_bytes(1000)
        + build_sint16_bytes(10)
        + encode_uint32(500)
        # No byte for is_alive (bit 4 set in bitvector = True)
    )

    result = decode_delta_packet(payload, spec, delta_cache)

    assert result["id"] == 1
    assert result["name"] == "player1"
    assert result["score"] == 1000
    assert result["level"] == 10
    assert result["gold"] == 500
    assert result["is_alive"] is True


@pytest.mark.integration
def test_delta_packet_round_trip(delta_cache):
    """Test encode → decode → verify match."""
    spec = create_test_packet_spec(
        packet_type=108,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "message", "type_name": "STRING"},
            {"name": "counter", "type_name": "SINT32"},
        ],
    )

    # Original values
    original = {"id": 42, "message": "test message", "counter": -999}

    # Build payload manually
    payload = (
        b"\x03"  # Both non-key fields present
        + encode_uint32(original["id"])
        + encode_string(original["message"])
        + build_sint32_bytes(original["counter"])
    )

    # Decode
    result = decode_delta_packet(payload, spec, delta_cache)

    # Verify match
    assert result == original


@pytest.mark.integration
def test_delta_packet_cache_isolation(delta_cache):
    """Test that cache entries for different packet types are isolated."""
    # Spec 1
    spec1 = create_test_packet_spec(
        packet_type=109,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "value1", "type_name": "SINT32"},
        ],
    )

    # Spec 2 (different packet type)
    spec2 = create_test_packet_spec(
        packet_type=110,
        fields=[
            {"name": "id", "type_name": "UINT32", "is_key": True},
            {"name": "value2", "type_name": "SINT32"},
        ],
    )

    # Decode packet type 109
    payload1 = b"\x01" + encode_uint32(5) + build_sint32_bytes(100)
    decode_delta_packet(payload1, spec1, delta_cache)

    # Decode packet type 110 with same key
    payload2 = b"\x01" + encode_uint32(5) + build_sint32_bytes(200)
    decode_delta_packet(payload2, spec2, delta_cache)

    # Verify separate cache entries
    cached1 = delta_cache.get_cached_packet(109, (5,))
    cached2 = delta_cache.get_cached_packet(110, (5,))

    assert cached1["value1"] == 100
    assert cached2["value2"] == 200


@pytest.mark.integration
def test_delta_packet_spec_from_registry(delta_cache):
    """Test using PacketSpec from PACKET_SPECS registry."""
    # Use real PACKET_CHAT_MSG spec (packet type 25)
    if 25 not in PACKET_SPECS:
        pytest.skip("PACKET_CHAT_MSG not in registry")

    spec = PACKET_SPECS[25]

    # Build minimal CHAT_MSG packet (all fields present)
    # Fields: message, tile, event, turn, phase, conn_id
    payload = (
        encode_string("Hello")
        + build_sint32_bytes(0)
        + build_sint16_bytes(0)
        + build_sint16_bytes(1)
        + build_sint16_bytes(0)
        + build_sint16_bytes(-1)
    )

    # Add bitvector at the start (no key fields in CHAT_MSG)
    # 6 non-key fields, all present = 0x3F
    payload_with_bitvector = b"\x3f" + payload

    result = decode_delta_packet(payload_with_bitvector, spec, delta_cache)

    assert result["message"] == "Hello"
    assert result["turn"] == 1


@pytest.mark.integration
@pytest.mark.slow
def test_full_chat_msg_pipeline(delta_cache):
    """Test complete CHAT_MSG lifecycle with multiple packets."""
    if 25 not in PACKET_SPECS:
        pytest.skip("PACKET_CHAT_MSG not in registry")

    spec = PACKET_SPECS[25]

    # First message: all fields
    payload1 = (
        b"\x3f"  # All 6 bits set
        + encode_string("First message")
        + build_sint32_bytes(100)
        + build_sint16_bytes(1)
        + build_sint16_bytes(1)
        + build_sint16_bytes(0)
        + build_sint16_bytes(1)
    )
    result1 = decode_delta_packet(payload1, spec, delta_cache)
    assert result1["message"] == "First message"

    # Second message: only message changed
    payload2 = (
        b"\x01"  # Only bit 0 (message) set
        + encode_string("Second message")
        # Other fields from cache
    )
    result2 = decode_delta_packet(payload2, spec, delta_cache)
    assert result2["message"] == "Second message"
    assert result2["tile"] == 100  # From cache
    assert result2["turn"] == 1  # From cache


@pytest.mark.integration
def test_decode_server_join_reply_integration():
    """Test non-delta packet (SERVER_JOIN_REPLY) integration."""
    # Build complete JOIN_REPLY payload
    payload = (
        encode_bool(True)
        + encode_string("Welcome to the game!")
        + encode_string("+Freeciv-3.0-network")
        + encode_string("")
        + encode_sint16(1)  # conn_id
    )

    result = decode_server_join_reply(payload)

    assert result["you_can_join"] is True
    assert result["message"] == "Welcome to the game!"
    assert result["capability"] == "+Freeciv-3.0-network"
    assert result["conn_id"] == 1


@pytest.mark.integration
def test_decode_server_info_integration():
    """Test non-delta packet (SERVER_INFO) integration."""
    # Build complete SERVER_INFO payload
    payload = (
        encode_string("3.0.90-dev")
        + encode_uint32(3)
        + encode_uint32(0)
        + encode_uint32(90)
        + encode_uint32(0)
    )

    result = decode_server_info(payload)

    assert result["version_label"] == "3.0.90-dev"
    assert result["major_version"] == 3
    assert result["minor_version"] == 0
    assert result["patch_version"] == 90
    assert result["emerg_version"] == 0


# ============================================================================
# PACKET_RULESET_TECH_FLAG Integration Tests
# ============================================================================


@pytest.mark.integration
def test_ruleset_tech_flag_handler_stores_in_game_state(freeciv_client, game_state):
    """Test that handle_ruleset_tech_flag stores tech flag in game_state.tech_flags."""
    from fc_client.handlers.ruleset import handle_ruleset_tech_flag
    from fc_client.protocol import encode_string

    # Build packet payload with all fields
    payload = (
        b"\x07"  # All 3 bits set
        b"\x01"  # id: 1
        b"Prerequisite\x00"  # name
        b"Technology has a prerequisite.\x00"  # helptxt
    )

    # Call handler
    import asyncio

    asyncio.run(handle_ruleset_tech_flag(freeciv_client, game_state, payload))

    # Verify tech flag was stored
    assert 1 in game_state.tech_flags
    tech_flag = game_state.tech_flags[1]
    assert tech_flag.id == 1
    assert tech_flag.name == "Prerequisite"
    assert tech_flag.helptxt == "Technology has a prerequisite."


@pytest.mark.integration
def test_ruleset_tech_flag_handler_multiple_flags(freeciv_client, game_state):
    """Test that multiple tech flags are stored correctly."""
    from fc_client.handlers.ruleset import handle_ruleset_tech_flag

    # First tech flag
    payload1 = (
        b"\x07"  # All fields
        b"\x00"  # id: 0
        b"Bonus_Tech\x00"
        b"Provides research bonus.\x00"
    )

    # Second tech flag
    payload2 = (
        b"\x07"  # All fields
        b"\x01"  # id: 1
        b"Root_Req\x00"
        b"Root requirement flag.\x00"
    )

    # Third tech flag
    payload3 = (
        b"\x07"  # All fields
        b"\x02"  # id: 2
        b"Special\x00"
        b"Special technology flag.\x00"
    )

    # Call handlers
    import asyncio

    asyncio.run(handle_ruleset_tech_flag(freeciv_client, game_state, payload1))
    asyncio.run(handle_ruleset_tech_flag(freeciv_client, game_state, payload2))
    asyncio.run(handle_ruleset_tech_flag(freeciv_client, game_state, payload3))

    # Verify all three are stored
    assert len(game_state.tech_flags) == 3
    assert 0 in game_state.tech_flags
    assert 1 in game_state.tech_flags
    assert 2 in game_state.tech_flags

    # Verify each tech flag
    assert game_state.tech_flags[0].name == "Bonus_Tech"
    assert game_state.tech_flags[1].name == "Root_Req"
    assert game_state.tech_flags[2].name == "Special"


@pytest.mark.integration
def test_ruleset_tech_flag_handler_with_delta_cache(freeciv_client, game_state):
    """Test that handler works correctly with delta cache updates."""
    from fc_client.handlers.ruleset import handle_ruleset_tech_flag

    # First packet: all fields
    payload1 = (
        b"\x07"  # All fields
        b"\x05"  # id: 5
        b"Initial_Name\x00"
        b"Initial help text.\x00"
    )

    # Second packet: only name changes (uses delta cache)
    payload2 = (
        b"\x02"  # Only bit 1 set (name)
        b"Updated_Name\x00"
    )

    # Call handlers
    import asyncio

    asyncio.run(handle_ruleset_tech_flag(freeciv_client, game_state, payload1))
    asyncio.run(handle_ruleset_tech_flag(freeciv_client, game_state, payload2))

    # Verify final state has updated name but cached id and helptxt
    tech_flag = game_state.tech_flags[5]
    assert tech_flag.id == 5  # From cache (not transmitted in 2nd packet)
    assert tech_flag.name == "Updated_Name"  # Updated value
    assert tech_flag.helptxt == "Initial help text."  # From cache
