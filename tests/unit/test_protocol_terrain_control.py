"""Tests for PACKET_RULESET_TERRAIN_CONTROL (146) decoding."""

import pytest
from fc_client.protocol import decode_ruleset_terrain_control, PACKET_RULESET_TERRAIN_CONTROL
from fc_client.delta_cache import DeltaCache


def test_decode_ruleset_terrain_control_full_packet():
    """Test decoding PACKET_RULESET_TERRAIN_CONTROL with all fields present.

    This test uses captured packet data from a real FreeCiv server.
    Bitvector: 0x0cd3 (little-endian) = bits 0,1,4,6,7,10,11 set
    """
    # Real packet captured from server (without packet header)
    # Bitvector (2 bytes) + field data
    payload = bytes(
        [
            0xD3,
            0x0C,  # Bitvector: bits 0,1,4,6,7,10,11 set
            0x1E,  # Bit 0: ocean_reclaim_requirement_pct = 30
            0x0A,  # Bit 1: land_channel_requirement_pct = 10
            0x0E,  # Bit 4: lake_max_size = 14
            0x00,
            0x00,
            0x00,
            0x06,  # Bit 6: move_fragments = 6 (big-endian)
            0x00,
            0x00,
            0x00,
            0x02,  # Bit 7: igter_cost = 2 (big-endian)
            # Bit 8: pythagorean_diagonal = False (header-folded, no bytes)
            # Bit 9: infrapoints = False (header-folded, no bytes)
            # Bit 10: gui_type_base0 (string)
            0x3F,
            0x67,
            0x75,
            0x69,
            0x5F,
            0x74,
            0x79,
            0x70,
            0x65,
            0x3A,
            0x42,
            0x75,
            0x69,
            0x6C,
            0x64,
            0x20,
            0x46,
            0x6F,
            0x72,
            0x74,
            0x2F,
            0x46,
            0x6F,
            0x72,
            0x74,
            0x72,
            0x65,
            0x73,
            0x73,
            0x2F,
            0x42,
            0x75,
            0x6F,
            0x79,
            0x00,  # "?gui_type:Build Fort/Fortress/Buoy\0"
            # Bit 11: gui_type_base1 (string)
            0x3F,
            0x67,
            0x75,
            0x69,
            0x5F,
            0x74,
            0x79,
            0x70,
            0x65,
            0x3A,
            0x42,
            0x75,
            0x69,
            0x6C,
            0x64,
            0x20,
            0x41,
            0x69,
            0x72,
            0x73,
            0x74,
            0x72,
            0x69,
            0x70,
            0x2F,
            0x41,
            0x69,
            0x72,
            0x62,
            0x61,
            0x73,
            0x65,
            0x00,  # "?gui_type:Build Airstrip/Airbase\0"
        ]
    )

    delta_cache = DeltaCache()
    result = decode_ruleset_terrain_control(payload, delta_cache)

    # Verify all fields
    assert result["ocean_reclaim_requirement_pct"] == 30
    assert result["land_channel_requirement_pct"] == 10
    assert result["terrain_thaw_requirement_pct"] == 0  # Not in packet, default value
    assert result["terrain_freeze_requirement_pct"] == 0  # Not in packet, default value
    assert result["lake_max_size"] == 14
    assert result["min_start_native_area"] == 0  # Not in packet, default value
    assert result["move_fragments"] == 6
    assert result["igter_cost"] == 2
    assert result["pythagorean_diagonal"] is False
    assert result["infrapoints"] is False
    assert result["gui_type_base0"] == "?gui_type:Build Fort/Fortress/Buoy"
    assert result["gui_type_base1"] == "?gui_type:Build Airstrip/Airbase"


def test_decode_ruleset_terrain_control_boolean_header_folding():
    """Test that boolean fields use header folding (bitvector bit is the value)."""
    # Bitvector with bits 8 and 9 set (pythagorean_diagonal and infrapoints)
    # 0x0300 = 00000011 00000000 (bits 8 and 9 set)
    payload = bytes(
        [
            0x00,
            0x03,  # Bitvector: bits 8,9 set
            # No payload bytes for bits 8 and 9 - they're header-folded!
        ]
    )

    delta_cache = DeltaCache()
    result = decode_ruleset_terrain_control(payload, delta_cache)

    # Boolean fields should be True (from bitvector), no payload consumed
    assert result["pythagorean_diagonal"] is True
    assert result["infrapoints"] is True

    # All other fields should have default values
    assert result["ocean_reclaim_requirement_pct"] == 0
    assert result["land_channel_requirement_pct"] == 0
    assert result["terrain_thaw_requirement_pct"] == 0
    assert result["terrain_freeze_requirement_pct"] == 0
    assert result["lake_max_size"] == 0
    assert result["min_start_native_area"] == 0
    assert result["move_fragments"] == 0
    assert result["igter_cost"] == 0
    assert result["gui_type_base0"] == ""
    assert result["gui_type_base1"] == ""


def test_decode_ruleset_terrain_control_delta_protocol():
    """Test delta protocol caching with partial updates."""
    delta_cache = DeltaCache()

    # First packet: set initial values
    payload1 = bytes(
        [
            0xFF,
            0x0F,  # Bitvector: all 12 bits set
            30,  # ocean_reclaim_requirement_pct
            10,  # land_channel_requirement_pct
            5,  # terrain_thaw_requirement_pct
            8,  # terrain_freeze_requirement_pct
            14,  # lake_max_size
            20,  # min_start_native_area
            0,
            0,
            0,
            6,  # move_fragments (big-endian)
            0,
            0,
            0,
            2,  # igter_cost (big-endian)
            # Bits 8,9 are True (in bitvector)
            ord("A"),
            0,  # gui_type_base0 = "A"
            ord("B"),
            0,  # gui_type_base1 = "B"
        ]
    )

    result1 = decode_ruleset_terrain_control(payload1, delta_cache)
    assert result1["ocean_reclaim_requirement_pct"] == 30
    assert result1["lake_max_size"] == 14
    assert result1["pythagorean_diagonal"] is True
    assert result1["gui_type_base0"] == "A"

    # Second packet: update lake_max_size, gui_type_base0, and turn off pythagorean_diagonal
    # Bit 4 (lake_max_size), bit 9 (infrapoints), and bit 10 (gui_type_base0)
    # Note: Bits 8-9 are header-folded, so their value comes from bitvector (not cached)
    payload2 = bytes(
        [
            0x10,
            0x06,  # Bitvector: bits 4, 9, and 10 set
            20,  # lake_max_size (updated to 20)
            # Bit 9 (infrapoints) = True from bitvector, no payload bytes
            ord("C"),
            0,  # gui_type_base0 (updated to "C")
        ]
    )

    result2 = decode_ruleset_terrain_control(payload2, delta_cache)

    # Updated fields
    assert result2["lake_max_size"] == 20
    assert result2["gui_type_base0"] == "C"

    # Cached fields (unchanged from first packet)
    assert result2["ocean_reclaim_requirement_pct"] == 30
    assert result2["land_channel_requirement_pct"] == 10
    assert result2["terrain_thaw_requirement_pct"] == 5
    assert result2["terrain_freeze_requirement_pct"] == 8
    assert result2["min_start_native_area"] == 20
    assert result2["move_fragments"] == 6
    assert result2["igter_cost"] == 2
    assert result2["gui_type_base1"] == "B"  # Unchanged

    # Header-folded booleans always come from current packet's bitvector (not cached)
    assert result2["pythagorean_diagonal"] is False  # Bit 8 not set in packet 2
    assert result2["infrapoints"] is True  # Bit 9 set in packet 2


def test_decode_ruleset_terrain_control_uint32_fields():
    """Test that move_fragments and igter_cost are decoded as UINT32 (4 bytes, big-endian)."""
    # Bitvector with bits 6 and 7 set (move_fragments and igter_cost)
    payload = bytes(
        [
            0xC0,
            0x00,  # Bitvector: bits 6,7 set
            0x12,
            0x34,
            0x56,
            0x78,  # move_fragments = 0x12345678 (big-endian)
            0xAB,
            0xCD,
            0xEF,
            0x01,  # igter_cost = 0xabcdef01 (big-endian)
        ]
    )

    delta_cache = DeltaCache()
    result = decode_ruleset_terrain_control(payload, delta_cache)

    assert result["move_fragments"] == 0x12345678
    assert result["igter_cost"] == 0xABCDEF01


def test_decode_ruleset_terrain_control_empty_strings():
    """Test decoding with empty GUI type strings."""
    payload = bytes(
        [
            0x00,
            0x0C,  # Bitvector: bits 10,11 set
            0x00,  # Empty string for gui_type_base0
            0x00,  # Empty string for gui_type_base1
        ]
    )

    delta_cache = DeltaCache()
    result = decode_ruleset_terrain_control(payload, delta_cache)

    assert result["gui_type_base0"] == ""
    assert result["gui_type_base1"] == ""
