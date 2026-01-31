"""Tests for PACKET_RULESET_CLAUSE (512) decoding."""

import pytest
from fc_client.protocol import decode_ruleset_clause, PACKET_RULESET_CLAUSE
from fc_client.delta_cache import DeltaCache


def test_decode_ruleset_clause_empty_bitvector_with_cache():
    """Test decoding PACKET_RULESET_CLAUSE with empty bitvector (cache-only update).

    This represents a packet that doesn't change any fields, relying entirely
    on cached values. This is common when the server sends incremental updates.

    IMPORTANT: The 'enabled' field uses boolean header folding, which means it's
    ALWAYS transmitted via the bitvector itself. When bit 1 is not set in the
    bitvector, enabled is False, regardless of cache.
    """
    cache = DeltaCache()

    # Pre-populate cache with a clause type
    cache.update_cache(
        PACKET_RULESET_CLAUSE,
        (),  # Empty tuple for hash_const
        {
            "type": 5,
            "enabled": True,  # This will NOT be preserved if bit 1 is not set
            "giver_reqs_count": 0,
            "giver_reqs": [],
            "receiver_reqs_count": 0,
            "receiver_reqs": [],
        },
    )

    # Empty bitvector (no fields present)
    # Bit 1 NOT set means enabled=False (boolean header folding)
    payload = bytes([0x00])

    result = decode_ruleset_clause(payload, cache)

    # Should return cached values except enabled
    assert result["type"] == 5  # From cache
    assert result["enabled"] is False  # From bitvector bit 1 (not set)
    assert result["giver_reqs_count"] == 0
    assert result["giver_reqs"] == []
    assert result["receiver_reqs_count"] == 0
    assert result["receiver_reqs"] == []


def test_decode_ruleset_clause_type_and_enabled():
    """Test decoding PACKET_RULESET_CLAUSE with type and enabled fields.

    Tests boolean header folding for the enabled field - when bit 1 is set,
    enabled=True, and NO payload bytes are consumed.
    """
    cache = DeltaCache()

    # Bitvector: bits 0 and 1 set (0x03)
    # Bit 0: type field present
    # Bit 1: enabled = True (boolean header folding, no bytes)
    payload = bytes(
        [
            0x03,  # Bitvector: bits 0,1 set
            0x07,  # type = 7 (Alliance)
        ]
    )

    result = decode_ruleset_clause(payload, cache)

    assert result["type"] == 7
    assert result["enabled"] is True  # From bit 1 being set
    assert result["giver_reqs_count"] == 0
    assert result["giver_reqs"] == []
    assert result["receiver_reqs_count"] == 0
    assert result["receiver_reqs"] == []


def test_decode_ruleset_clause_type_disabled():
    """Test decoding PACKET_RULESET_CLAUSE with enabled=False.

    When bit 1 is NOT set, enabled should be False.
    """
    cache = DeltaCache()

    # Bitvector: only bit 0 set (0x01)
    # Bit 0: type field present
    # Bit 1: NOT set, so enabled = False
    payload = bytes(
        [
            0x01,  # Bitvector: only bit 0 set
            0x04,  # type = 4 (City)
        ]
    )

    result = decode_ruleset_clause(payload, cache)

    assert result["type"] == 4
    assert result["enabled"] is False  # Bit 1 not set
    assert result["giver_reqs_count"] == 0
    assert result["giver_reqs"] == []
    assert result["receiver_reqs_count"] == 0
    assert result["receiver_reqs"] == []


def test_decode_ruleset_clause_with_counts():
    """Test decoding PACKET_RULESET_CLAUSE with requirement counts."""
    cache = DeltaCache()

    # Bitvector: bits 0, 2, 4 set (0x15)
    # Bit 0: type
    # Bit 2: giver_reqs_count
    # Bit 4: receiver_reqs_count
    payload = bytes(
        [
            0x15,  # Bitvector: bits 0,2,4 set
            0x06,  # type = 6 (Peace)
            0x02,  # giver_reqs_count = 2
            0x03,  # receiver_reqs_count = 3
        ]
    )

    result = decode_ruleset_clause(payload, cache)

    assert result["type"] == 6
    assert result["enabled"] is False  # Bit 1 not set
    assert result["giver_reqs_count"] == 2
    assert result["giver_reqs"] == []  # Count set but no array data
    assert result["receiver_reqs_count"] == 3
    assert result["receiver_reqs"] == []


def test_decode_ruleset_clause_with_requirements():
    """Test decoding PACKET_RULESET_CLAUSE with full requirement arrays.

    Each requirement is 10 bytes: type(1) + value(4) + range(1) + survives(1)
                                  + present(1) + quiet(1)
    """
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

    # Bitvector: bits 0, 1, 2, 3 set (0x0F)
    # Bit 0: type
    # Bit 1: enabled = True (boolean header folding)
    # Bit 2: giver_reqs_count
    # Bit 3: giver_reqs array
    payload = bytes([0x0F, 0x08, 0x01]) + req1  # type=8, count=1, req1

    result = decode_ruleset_clause(payload, cache)

    assert result["type"] == 8  # Vision
    assert result["enabled"] is True
    assert result["giver_reqs_count"] == 1
    assert len(result["giver_reqs"]) == 1
    assert result["giver_reqs"][0]["type"] == 1
    assert result["giver_reqs"][0]["value"] == 10
    assert result["giver_reqs"][0]["range"] == 2
    assert result["giver_reqs"][0]["survives"] is False
    assert result["giver_reqs"][0]["present"] is True
    assert result["giver_reqs"][0]["quiet"] is False


def test_decode_ruleset_clause_with_both_requirement_arrays():
    """Test decoding PACKET_RULESET_CLAUSE with both giver and receiver requirements."""
    cache = DeltaCache()

    # Create two mock requirements (10 bytes each)
    # req1: type=1, value=10, range=2, survives=F, present=T, quiet=F
    req1 = bytes([0x01, 0x00, 0x00, 0x00, 0x0A, 0x02, 0x00, 0x01, 0x00])
    # req2: type=2, value=12, range=1, survives=T, present=F, quiet=T
    req2 = bytes([0x02, 0x00, 0x00, 0x00, 0x0C, 0x01, 0x01, 0x00, 0x01])

    # Bitvector: all bits 0-5 set (0x3F)
    payload = (
        bytes(
            [
                0x3F,  # Bitvector: all 6 bits set
                0x09,  # type = 9 (Embassy)
                # enabled = True (bit 1 set, no bytes)
                0x01,  # giver_reqs_count = 1
            ]
        )
        + req1  # giver_reqs[0]
        + bytes([0x01])  # receiver_reqs_count = 1
        + req2  # receiver_reqs[0]
    )

    result = decode_ruleset_clause(payload, cache)

    assert result["type"] == 9
    assert result["enabled"] is True
    assert result["giver_reqs_count"] == 1
    assert len(result["giver_reqs"]) == 1
    assert result["receiver_reqs_count"] == 1
    assert len(result["receiver_reqs"]) == 1

    # Verify first requirement (giver)
    assert result["giver_reqs"][0]["type"] == 1
    assert result["giver_reqs"][0]["value"] == 10
    assert result["giver_reqs"][0]["range"] == 2

    # Verify second requirement (receiver)
    assert result["receiver_reqs"][0]["type"] == 2
    assert result["receiver_reqs"][0]["value"] == 12
    assert result["receiver_reqs"][0]["range"] == 1


def test_decode_ruleset_clause_delta_caching():
    """Test that delta caching works correctly with empty tuple key.

    IMPORTANT: Boolean header folding fields (like 'enabled') are ALWAYS
    transmitted via the bitvector, so they don't benefit from caching.
    """
    cache = DeltaCache()

    # First packet: set type and enabled
    payload1 = bytes([0x03, 0x05])  # bits 0,1; type=5, enabled=True
    result1 = decode_ruleset_clause(payload1, cache)
    assert result1["type"] == 5
    assert result1["enabled"] is True

    # Second packet: update counts only (type from cache, enabled from bitvector)
    # Bit 1 NOT set, so enabled=False (not from cache!)
    payload2 = bytes([0x14, 0x02, 0x01])  # bits 2,4; giver_count=2, receiver_count=1
    result2 = decode_ruleset_clause(payload2, cache)
    assert result2["type"] == 5  # From cache
    assert result2["enabled"] is False  # From bitvector (bit 1 not set)
    assert result2["giver_reqs_count"] == 2
    assert result2["receiver_reqs_count"] == 1

    # Third packet: empty bitvector (type and counts from cache, enabled from bitvector)
    payload3 = bytes([0x00])
    result3 = decode_ruleset_clause(payload3, cache)
    assert result3["type"] == 5
    assert result3["enabled"] is False  # From bitvector (bit 1 not set)
    assert result3["giver_reqs_count"] == 2
    assert result3["receiver_reqs_count"] == 1


def test_decode_ruleset_clause_real_captured_packet():
    """Test decoding the real captured PACKET_RULESET_CLAUSE from FreeCiv server.

    This is the actual packet captured from packets/inbound_2498_type512.packet
    """
    cache = DeltaCache()

    # Real captured packet (5 bytes)
    payload = bytes([0x00, 0x05, 0x02, 0x00, 0x02])

    # The packet has empty bitvector, so all fields come from cache or are ignored
    # This suggests it's a cache-only update
    result = decode_ruleset_clause(payload, cache)

    # With no cache, should get defaults
    assert result["type"] == 0
    assert result["enabled"] is False
    assert result["giver_reqs_count"] == 0
    assert result["giver_reqs"] == []
    assert result["receiver_reqs_count"] == 0
    assert result["receiver_reqs"] == []


def test_decode_ruleset_clause_all_clause_types():
    """Test that all clause types (0-10) can be decoded."""
    cache = DeltaCache()

    clause_types = [
        (0, "Advance"),
        (1, "Gold"),
        (2, "Map"),
        (3, "Seamap"),
        (4, "City"),
        (5, "Ceasefire"),
        (6, "Peace"),
        (7, "Alliance"),
        (8, "Vision"),
        (9, "Embassy"),
        (10, "SharedTiles"),
    ]

    for clause_type, name in clause_types:
        payload = bytes([0x01, clause_type])  # bit 0 set, type field
        result = decode_ruleset_clause(payload, cache)
        assert result["type"] == clause_type, f"Failed for {name}"
        assert result["enabled"] is False


def test_decode_ruleset_clause_cache_isolation():
    """Test that cache updates use empty tuple key and don't interfere with other packets."""
    cache = DeltaCache()

    # Update clause cache
    payload = bytes([0x03, 0x05])  # type=5, enabled=True
    result = decode_ruleset_clause(payload, cache)

    # Verify cache is stored with empty tuple key
    cached = cache.get_cached_packet(PACKET_RULESET_CLAUSE, ())
    assert cached is not None
    assert cached["type"] == 5
    assert cached["enabled"] is True

    # Verify a different key doesn't retrieve this cache
    cached_wrong_key = cache.get_cached_packet(PACKET_RULESET_CLAUSE, (1,))
    assert cached_wrong_key is None
