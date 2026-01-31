"""Integration tests for PACKET_GAME_INFO with array-diff protocol.

Tests the complete flow of decoding PACKET_GAME_INFO packets that use
array-diff optimization for global_advances and great_wonder_owners arrays.
"""

import pytest
from fc_client.protocol import decode_delta_packet, PACKET_SPECS
from fc_client.delta_cache import DeltaCache


class TestGameInfoArrayDiff:
    """Test PACKET_GAME_INFO decoding with array-diff fields."""

    def test_game_info_first_packet_empty_arrays(self):
        """Test decoding PACKET_GAME_INFO with no advances or wonders (empty arrays)."""
        # Minimal PACKET_GAME_INFO with:
        # - Bitvector (1 byte for 3 non-key fields)
        # - global_advance_count = 0
        # - global_advances array (empty, just sentinel)
        # - great_wonder_owners array (empty, just sentinel)

        # Bitvector: all 3 fields present (bits 0, 1, 2 set)
        # Bitvector = 0b00000111 = 0x07
        bitvector = bytes([0x07])

        # Field 0: global_advance_count = 0 (UINT16, big-endian)
        global_advance_count = bytes([0x00, 0x00])

        # Field 1: global_advances array-diff (empty, sentinel = 401)
        # Sentinel for A_LAST = 401 = 0x0191, uint16 big-endian = [0x01, 0x91]
        global_advances_sentinel = bytes([0x01, 0x91])

        # Field 2: great_wonder_owners array-diff (empty, sentinel = 200)
        # Sentinel = 200 = 0xC8, uint8 = [0xC8]
        great_wonder_owners_sentinel = bytes([0xC8])

        payload = (
            bitvector
            + global_advance_count
            + global_advances_sentinel
            + great_wonder_owners_sentinel
        )

        # Decode
        spec = PACKET_SPECS[16]
        cache = DeltaCache()
        result = decode_delta_packet(payload, spec, cache)

        # Verify
        assert result["global_advance_count"] == 0
        assert result["global_advances"] == [False] * 401  # All False (no advances)
        assert result["great_wonder_owners"] == [0] * 200  # All 0 (no owners)

    def test_game_info_with_some_advances(self):
        """Test decoding PACKET_GAME_INFO with some technologies discovered."""
        # Packet with:
        # - global_advance_count = 5
        # - global_advances: techs 0, 10, 20 discovered
        # - great_wonder_owners: empty

        # Bitvector: all 3 fields present
        bitvector = bytes([0x07])

        # Field 0: global_advance_count = 5 (UINT16)
        global_advance_count = bytes([0x00, 0x05])

        # Field 1: global_advances array-diff
        # Tech 0 = True, Tech 10 = True, Tech 20 = True, sentinel = 401
        # Indices are UINT16 (array_size=401 > 255)
        # Index 0 = 0x0000, big-endian = [0x00, 0x00]
        # Value True = 1
        # Index 10 = 0x000A, big-endian = [0x00, 0x0A]
        # Index 20 = 0x0014, big-endian = [0x00, 0x14]
        # Sentinel 401 = 0x0191, big-endian = [0x01, 0x91]
        global_advances_diff = bytes(
            [
                0x00,
                0x00,  # index 0
                0x01,  # value True
                0x00,
                0x0A,  # index 10
                0x01,  # value True
                0x00,
                0x14,  # index 20
                0x01,  # value True
                0x01,
                0x91,  # sentinel
            ]
        )

        # Field 2: great_wonder_owners array-diff (empty)
        great_wonder_owners_sentinel = bytes([0xC8])

        payload = (
            bitvector + global_advance_count + global_advances_diff + great_wonder_owners_sentinel
        )

        # Decode
        spec = PACKET_SPECS[16]
        cache = DeltaCache()
        result = decode_delta_packet(payload, spec, cache)

        # Verify
        assert result["global_advance_count"] == 5
        assert len(result["global_advances"]) == 401
        assert result["global_advances"][0] == True
        assert result["global_advances"][10] == True
        assert result["global_advances"][20] == True
        # All others should be False
        assert result["global_advances"][1] == False
        assert result["global_advances"][5] == False
        assert result["global_advances"][100] == False

    def test_game_info_with_wonders(self):
        """Test decoding PACKET_GAME_INFO with wonders owned by players."""
        # Packet with:
        # - global_advance_count = 0
        # - global_advances: empty
        # - great_wonder_owners: wonder 5 owned by player 1, wonder 10 by player 2

        # Bitvector: all 3 fields present
        bitvector = bytes([0x07])

        # Field 0: global_advance_count = 0
        global_advance_count = bytes([0x00, 0x00])

        # Field 1: global_advances (empty)
        global_advances_sentinel = bytes([0x01, 0x91])

        # Field 2: great_wonder_owners array-diff
        # Wonder 5 owned by player 1 (SINT8)
        # Wonder 10 owned by player 2 (SINT8)
        # Indices are UINT8 (array_size=200 <= 255)
        great_wonder_owners_diff = bytes(
            [
                5,  # index 5
                1,  # player 1 (SINT8 = 1)
                10,  # index 10
                2,  # player 2 (SINT8 = 2)
                200,  # sentinel
            ]
        )

        payload = (
            bitvector + global_advance_count + global_advances_sentinel + great_wonder_owners_diff
        )

        # Decode
        spec = PACKET_SPECS[16]
        cache = DeltaCache()
        result = decode_delta_packet(payload, spec, cache)

        # Verify
        assert len(result["great_wonder_owners"]) == 200
        assert result["great_wonder_owners"][5] == 1
        assert result["great_wonder_owners"][10] == 2
        # All others should be 0
        assert result["great_wonder_owners"][0] == 0
        assert result["great_wonder_owners"][50] == 0

    def test_game_info_delta_update(self):
        """Test delta protocol with cached arrays - only changed elements transmitted."""
        spec = PACKET_SPECS[16]
        cache = DeltaCache()

        # First packet: establish baseline
        bitvector1 = bytes([0x07])
        global_advance_count1 = bytes([0x00, 0x02])
        # Tech 5 and 10 discovered
        global_advances_diff1 = bytes(
            [
                0x00,
                0x05,  # index 5
                0x01,  # True
                0x00,
                0x0A,  # index 10
                0x01,  # True
                0x01,
                0x91,  # sentinel
            ]
        )
        great_wonder_owners_sentinel1 = bytes([0xC8])
        payload1 = (
            bitvector1
            + global_advance_count1
            + global_advances_diff1
            + great_wonder_owners_sentinel1
        )

        result1 = decode_delta_packet(payload1, spec, cache)
        assert result1["global_advance_count"] == 2
        assert result1["global_advances"][5] == True
        assert result1["global_advances"][10] == True

        # Second packet: update only global_advance_count and add tech 15
        # Bitvector: only fields 0 and 1 present (bits 0 and 1 set)
        # Bit 2 (great_wonder_owners) NOT set - will use cached value
        bitvector2 = bytes([0x03])
        global_advance_count2 = bytes([0x00, 0x03])
        # Only tech 15 added (techs 5 and 10 already in cache)
        global_advances_diff2 = bytes(
            [0x00, 0x0F, 0x01, 0x01, 0x91]  # index 15  # True  # sentinel
        )
        # No great_wonder_owners field in payload (using cached)
        payload2 = bitvector2 + global_advance_count2 + global_advances_diff2

        result2 = decode_delta_packet(payload2, spec, cache)
        assert result2["global_advance_count"] == 3
        # Array should have techs 5, 10, and 15
        assert result2["global_advances"][5] == True
        assert result2["global_advances"][10] == True
        assert result2["global_advances"][15] == True
        # great_wonder_owners should be from cache (all 0)
        assert len(result2["great_wonder_owners"]) == 200
        assert all(owner == 0 for owner in result2["great_wonder_owners"])
