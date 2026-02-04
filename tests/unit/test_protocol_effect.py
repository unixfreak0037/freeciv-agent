"""Tests for PACKET_RULESET_EFFECT (175) decoding."""

import pytest
from fc_client.protocol import decode_ruleset_effect, PACKET_RULESET_EFFECT
from fc_client.delta_cache import DeltaCache


def test_decode_ruleset_effect_all_fields():
    """Test decoding PACKET_RULESET_EFFECT with all fields present."""
    cache = DeltaCache()

    # Create a mock requirement (10 bytes)
    # type=1 (Tech), value=10, range=2, survives=False, present=True, quiet=False
    req1 = bytes(
        [
            0x01,  # type = 1 (UINT8)
            0x00,
            0x00,
            0x00,
            0x0A,  # value = 10 (SINT32 big-endian)
            0x02,  # range = 2 (UINT8)
            0x00,  # survives = False (BOOL8)
            0x01,  # present = True (BOOL8)
            0x00,  # quiet = False (BOOL8)
        ]
    )

    # Bitvector: all 6 bits set (0x3F)
    # Bit 0: effect_type
    # Bit 1: effect_value
    # Bit 2: has_multiplier = True (boolean header folding, no bytes)
    # Bit 3: multiplier
    # Bit 4: reqs_count
    # Bit 5: reqs array
    payload = (
        bytes(
            [
                0x3F,  # Bitvector: all 6 bits set
                0x1D,  # effect_type = 29 (UINT8)
                0x00,
                0x00,
                0x00,
                0x05,  # effect_value = 5 (SINT32 big-endian)
                # has_multiplier = True (bit 2 set, no bytes)
                0x02,  # multiplier = 2 (UINT8)
                0x01,  # reqs_count = 1 (UINT8)
            ]
        )
        + req1  # reqs[0]
    )

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_type"] == 29
    assert result["effect_value"] == 5
    assert result["has_multiplier"] is True
    assert result["multiplier"] == 2
    assert result["reqs_count"] == 1
    assert len(result["reqs"]) == 1
    assert result["reqs"][0]["type"] == 1
    assert result["reqs"][0]["value"] == 10


def test_decode_ruleset_effect_boolean_header_folding():
    """Test that has_multiplier uses boolean header folding (no payload bytes)."""
    cache = DeltaCache()

    # Bitvector: bits 0, 1, 2 set (0x07)
    # Bit 0: effect_type
    # Bit 1: effect_value
    # Bit 2: has_multiplier = True (no payload bytes!)
    payload = bytes(
        [
            0x07,  # Bitvector: bits 0,1,2 set
            0x05,  # effect_type = 5 (UINT8)
            0x00,
            0x00,
            0x00,
            0x0A,  # effect_value = 10 (SINT32)
            # NO bytes for has_multiplier - it's in the bitvector
        ]
    )

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_type"] == 5
    assert result["effect_value"] == 10
    assert result["has_multiplier"] is True  # From bitvector bit 2
    assert result["multiplier"] == 0  # Default (bit 3 not set)


def test_decode_ruleset_effect_no_multiplier():
    """Test decoding when has_multiplier is False (bit 2 not set)."""
    cache = DeltaCache()

    # Bitvector: bits 0, 1 set (0x03) - bit 2 NOT set
    payload = bytes(
        [
            0x03,  # Bitvector: bits 0,1 set
            0x08,  # effect_type = 8 (UINT8)
            0x00,
            0x00,
            0x00,
            0x14,  # effect_value = 20 (SINT32)
        ]
    )

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_type"] == 8
    assert result["effect_value"] == 20
    assert result["has_multiplier"] is False  # Bit 2 not set
    assert result["multiplier"] == 0


def test_decode_ruleset_effect_signed_value_positive():
    """Test decoding effect_value as signed integer (positive value)."""
    cache = DeltaCache()

    # Bitvector: bits 0, 1 set (0x03)
    payload = bytes(
        [
            0x03,  # Bitvector
            0x01,  # effect_type = 1
            0x00,
            0x00,
            0x00,
            0x64,  # effect_value = 100 (positive SINT32)
        ]
    )

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_value"] == 100


def test_decode_ruleset_effect_signed_value_negative():
    """Test decoding effect_value as signed integer (negative value)."""
    cache = DeltaCache()

    # Bitvector: bits 0, 1 set (0x03)
    payload = bytes(
        [
            0x03,  # Bitvector
            0x01,  # effect_type = 1
            0xFF,
            0xFF,
            0xFF,
            0x9C,  # effect_value = -100 (negative SINT32 big-endian)
        ]
    )

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_value"] == -100


def test_decode_ruleset_effect_delta_caching():
    """Test that delta caching works correctly with empty tuple key."""
    cache = DeltaCache()

    # First packet: set effect_type and effect_value
    payload1 = bytes(
        [
            0x03,  # bits 0,1
            0x0A,  # effect_type = 10
            0x00,
            0x00,
            0x00,
            0x14,  # effect_value = 20
        ]
    )
    result1 = decode_ruleset_effect(payload1, cache)
    assert result1["effect_type"] == 10
    assert result1["effect_value"] == 20
    assert result1["has_multiplier"] is False

    # Second packet: update only reqs_count (use cached values)
    payload2 = bytes(
        [
            0x10,  # bit 4 only (reqs_count)
            0x03,  # reqs_count = 3
        ]
    )
    result2 = decode_ruleset_effect(payload2, cache)
    assert result2["effect_type"] == 10  # From cache
    assert result2["effect_value"] == 20  # From cache
    assert result2["has_multiplier"] is False  # From bitvector (bit 2 not set)
    assert result2["reqs_count"] == 3

    # Third packet: set has_multiplier and multiplier
    payload3 = bytes(
        [
            0x0C,  # bits 2,3 (has_multiplier, multiplier)
            0x05,  # multiplier = 5
        ]
    )
    result3 = decode_ruleset_effect(payload3, cache)
    assert result3["effect_type"] == 10  # From cache
    assert result3["effect_value"] == 20  # From cache
    assert result3["has_multiplier"] is True  # From bitvector bit 2
    assert result3["multiplier"] == 5
    assert result3["reqs_count"] == 3  # From cache


def test_decode_ruleset_effect_multiple_requirements():
    """Test decoding with multiple requirements in the array."""
    cache = DeltaCache()

    # Create two mock requirements
    req1 = bytes([0x01, 0x00, 0x00, 0x00, 0x0A, 0x02, 0x00, 0x01, 0x00])
    req2 = bytes([0x02, 0x00, 0x00, 0x00, 0x14, 0x01, 0x01, 0x00, 0x01])

    # Bitvector: bits 0, 1, 4, 5 set (0x33)
    payload = (
        bytes(
            [
                0x33,  # Bitvector
                0x07,  # effect_type = 7
                0x00,
                0x00,
                0x00,
                0x0F,  # effect_value = 15
                0x02,  # reqs_count = 2
            ]
        )
        + req1
        + req2
    )

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_type"] == 7
    assert result["effect_value"] == 15
    assert result["reqs_count"] == 2
    assert len(result["reqs"]) == 2
    assert result["reqs"][0]["type"] == 1
    assert result["reqs"][0]["value"] == 10
    assert result["reqs"][1]["type"] == 2
    assert result["reqs"][1]["value"] == 20


def test_decode_ruleset_effect_empty_bitvector_with_cache():
    """Test decoding with empty bitvector (all fields from cache)."""
    cache = DeltaCache()

    # Pre-populate cache
    cache.update_cache(
        PACKET_RULESET_EFFECT,
        (),  # Empty tuple for hash_const
        {
            "effect_type": 15,
            "effect_value": 50,
            "has_multiplier": True,  # Will NOT be preserved (boolean header folding)
            "multiplier": 3,
            "reqs_count": 1,
            "reqs": [],
        },
    )

    # Empty bitvector
    payload = bytes([0x00])

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_type"] == 15  # From cache
    assert result["effect_value"] == 50  # From cache
    assert result["has_multiplier"] is False  # From bitvector (bit 2 not set)
    assert result["multiplier"] == 3  # From cache
    assert result["reqs_count"] == 1  # From cache


def test_decode_ruleset_effect_real_captured_packet():
    """Test decoding the real captured PACKET_RULESET_EFFECT from FreeCiv server.

    This is packet from packets/inbound_2530_type175.packet (29 bytes).
    Hex: 00 1d 00 af 33 45 ff ff ff ff 02 0d 00 00 00 05
         07 00 01 00 0a 00 00 00 00 00 00 01 00
    """
    cache = DeltaCache()

    # Real captured packet (skip first 3 bytes which are packet header)
    # Payload starts after the 3-byte header
    payload = bytes(
        [
            0x00,  # Bitvector: all bits 0 (empty)
            0x1D,
            0x00,
            0xAF,
            0x33,
            0x45,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0x02,
            0x0D,
            0x00,
            0x00,
            0x00,
            0x05,
            0x07,
            0x00,
            0x01,
            0x00,
            0x0A,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
        ]
    )

    # With empty bitvector, all fields should be defaults
    result = decode_ruleset_effect(payload, cache)

    assert result["effect_type"] == 0
    assert result["effect_value"] == 0
    assert result["has_multiplier"] is False
    assert result["multiplier"] == 0
    assert result["reqs_count"] == 0
    assert result["reqs"] == []


def test_decode_ruleset_effect_cache_isolation():
    """Test that cache updates use empty tuple key and don't interfere."""
    cache = DeltaCache()

    # Update effect cache
    payload = bytes(
        [
            0x03,  # bits 0,1
            0x0B,  # effect_type = 11
            0x00,
            0x00,
            0x00,
            0x1E,  # effect_value = 30
        ]
    )
    result = decode_ruleset_effect(payload, cache)

    # Verify cache is stored with empty tuple key
    cached = cache.get_cached_packet(PACKET_RULESET_EFFECT, ())
    assert cached is not None
    assert cached["effect_type"] == 11
    assert cached["effect_value"] == 30

    # Verify a different key doesn't retrieve this cache
    cached_wrong_key = cache.get_cached_packet(PACKET_RULESET_EFFECT, (1,))
    assert cached_wrong_key is None


def test_decode_ruleset_effect_zero_requirements():
    """Test decoding with reqs_count=0 but reqs array bit set."""
    cache = DeltaCache()

    # Bitvector: bits 0, 1, 4, 5 set (0x33)
    # reqs_count = 0, so no requirements should be read
    payload = bytes(
        [
            0x33,  # Bitvector
            0x03,  # effect_type = 3
            0x00,
            0x00,
            0x00,
            0x02,  # effect_value = 2
            0x00,  # reqs_count = 0
            # No requirement data follows
        ]
    )

    result = decode_ruleset_effect(payload, cache)

    assert result["effect_type"] == 3
    assert result["effect_value"] == 2
    assert result["reqs_count"] == 0
    assert result["reqs"] == []


def test_decode_ruleset_effect_common_effect_types():
    """Test that common effect types can be decoded."""
    cache = DeltaCache()

    effect_types = [
        0,  # TechParasite
        1,  # Airlift
        7,  # Output_Bonus
        24,  # Move_Bonus
        36,  # Make_Happy
        50,  # Inspire_Partisans
    ]

    for effect_type in effect_types:
        payload = bytes(
            [
                0x03,  # bits 0,1
                effect_type,
                0x00,
                0x00,
                0x00,
                0x01,  # effect_value = 1
            ]
        )
        result = decode_ruleset_effect(payload, cache)
        assert result["effect_type"] == effect_type
        assert result["effect_value"] == 1
