"""
Integration tests for PACKET_RULESET_BASE (153) - base type definitions.

Tests decoding, delta protocol caching, and handler functionality for base types
(military installations like forts, airbases, radar towers).
"""

import pytest
from fc_client import protocol
from fc_client.delta_cache import DeltaCache
from fc_client.game_state import GameState, BaseType
from fc_client.handlers.ruleset import handle_ruleset_base


class MockClient:
    """Mock client for testing handlers."""

    def __init__(self):
        self._delta_cache = DeltaCache()


class TestDecodeRulesetBase:
    """Test suite for decode_ruleset_base function."""

    def test_decode_captured_packet(self):
        """Test decoding actual captured packet from FreeCiv server.

        Captured packet: packets/inbound_2356_type153.packet
        Structure: bitvector=0x3c, four SINT8 values all -1
        Bitvector 0x3c = 0b00111100 (bits 2,3,4,5 set)
        """
        # Payload from captured packet (without packet header)
        payload = bytes([0x3C, 0xFF, 0xFF, 0xFF, 0xFF])

        delta_cache = DeltaCache()

        # First, we need to cache id and gui_type since the captured packet
        # doesn't send them (bitvector bits 0,1 are not set)
        # Simulate a previous packet that sent all fields
        initial_data = {
            "id": 0,
            "gui_type": 2,  # "Other" type
            "border_sq": -1,
            "vision_main_sq": -1,
            "vision_invis_sq": -1,
            "vision_subs_sq": -1,
        }
        delta_cache.update_cache(protocol.PACKET_RULESET_BASE, (), initial_data)

        # Now decode the captured packet
        result = protocol.decode_ruleset_base(payload, delta_cache)

        # Verify all fields
        assert result["id"] == 0  # From cache
        assert result["gui_type"] == 2  # From cache
        assert result["border_sq"] == -1  # From payload (SINT8 0xff = -1)
        assert result["vision_main_sq"] == -1  # From payload
        assert result["vision_invis_sq"] == -1  # From payload
        assert result["vision_subs_sq"] == -1  # From payload

    def test_decode_all_fields_present(self):
        """Test decoding when all fields are present in the packet."""
        # Bitvector 0x3f = 0b00111111 (all 6 bits set)
        # id=1, gui_type=0 (Fortress), border_sq=5, vision fields=2,3,4
        payload = bytes(
            [
                0x3F,  # Bitvector
                0x01,  # id (UINT8)
                0x00,  # gui_type (UINT8) - Fortress
                0x05,  # border_sq (SINT8) = 5
                0x02,  # vision_main_sq (SINT8) = 2
                0x03,  # vision_invis_sq (SINT8) = 3
                0x04,  # vision_subs_sq (SINT8) = 4
            ]
        )

        delta_cache = DeltaCache()
        result = protocol.decode_ruleset_base(payload, delta_cache)

        assert result["id"] == 1
        assert result["gui_type"] == 0  # Fortress
        assert result["border_sq"] == 5
        assert result["vision_main_sq"] == 2
        assert result["vision_invis_sq"] == 3
        assert result["vision_subs_sq"] == 4

    def test_decode_airbase_type(self):
        """Test decoding an airbase base type."""
        # Bitvector 0x03 = 0b00000011 (bits 0,1 set - id and gui_type only)
        payload = bytes([0x03, 0x02, 0x01])  # Bitvector  # id (UINT8)  # gui_type (UINT8) - Airbase

        delta_cache = DeltaCache()
        result = protocol.decode_ruleset_base(payload, delta_cache)

        assert result["id"] == 2
        assert result["gui_type"] == 1  # Airbase
        # Vision fields should use defaults
        assert result["border_sq"] == -1
        assert result["vision_main_sq"] == -1
        assert result["vision_invis_sq"] == -1
        assert result["vision_subs_sq"] == -1

    def test_decode_negative_values(self):
        """Test decoding negative SINT8 values correctly."""
        # Bitvector 0x3c = 0b00111100 (bits 2,3,4,5 set)
        # All vision values are -1 (0xff in two's complement)
        payload = bytes(
            [
                0x3C,  # Bitvector
                0xFF,  # border_sq (SINT8) = -1
                0xFF,  # vision_main_sq (SINT8) = -1
                0xFF,  # vision_invis_sq (SINT8) = -1
                0xFF,  # vision_subs_sq (SINT8) = -1
            ]
        )

        delta_cache = DeltaCache()
        result = protocol.decode_ruleset_base(payload, delta_cache)

        # All vision fields should decode to -1
        assert result["border_sq"] == -1
        assert result["vision_main_sq"] == -1
        assert result["vision_invis_sq"] == -1
        assert result["vision_subs_sq"] == -1

    def test_delta_protocol_caching(self):
        """Test that delta protocol correctly caches and retrieves values."""
        delta_cache = DeltaCache()

        # First packet: send all fields
        payload1 = bytes(
            [
                0x3F,  # All fields present
                0x01,  # id
                0x00,  # gui_type (Fortress)
                0x05,  # border_sq
                0x02,  # vision_main_sq
                0x03,  # vision_invis_sq
                0x04,  # vision_subs_sq
            ]
        )

        result1 = protocol.decode_ruleset_base(payload1, delta_cache)
        assert result1["id"] == 1
        assert result1["gui_type"] == 0

        # Second packet: only update vision fields (bits 2,3,4,5)
        payload2 = bytes(
            [
                0x3C,  # Only vision fields
                0x06,  # border_sq (new value)
                0x07,  # vision_main_sq (new value)
                0x08,  # vision_invis_sq (new value)
                0x09,  # vision_subs_sq (new value)
            ]
        )

        result2 = protocol.decode_ruleset_base(payload2, delta_cache)

        # id and gui_type should come from cache
        assert result2["id"] == 1
        assert result2["gui_type"] == 0
        # Vision fields should be updated
        assert result2["border_sq"] == 6
        assert result2["vision_main_sq"] == 7
        assert result2["vision_invis_sq"] == 8
        assert result2["vision_subs_sq"] == 9

    def test_empty_bitvector(self):
        """Test decoding with empty bitvector (all values from cache/defaults)."""
        # Bitvector 0x00 = no fields present
        payload = bytes([0x00])

        delta_cache = DeltaCache()

        # Set up cache with previous values
        cached_data = {
            "id": 5,
            "gui_type": 1,
            "border_sq": 10,
            "vision_main_sq": 8,
            "vision_invis_sq": 6,
            "vision_subs_sq": 4,
        }
        delta_cache.update_cache(protocol.PACKET_RULESET_BASE, (), cached_data)

        result = protocol.decode_ruleset_base(payload, delta_cache)

        # All values should come from cache
        assert result["id"] == 5
        assert result["gui_type"] == 1
        assert result["border_sq"] == 10
        assert result["vision_main_sq"] == 8
        assert result["vision_invis_sq"] == 6
        assert result["vision_subs_sq"] == 4


class TestHandleRulesetBase:
    """Test suite for handle_ruleset_base handler function."""

    @pytest.mark.asyncio
    async def test_handler_stores_base_type(self):
        """Test that handler correctly stores BaseType in game state."""
        game_state = GameState()
        client = MockClient()

        # Payload with all fields
        payload = bytes(
            [
                0x3F,  # All fields present
                0x01,  # id
                0x00,  # gui_type (Fortress)
                0x05,  # border_sq
                0x02,  # vision_main_sq
                0x03,  # vision_invis_sq
                0x04,  # vision_subs_sq
            ]
        )

        await handle_ruleset_base(client, game_state, payload)

        # Verify BaseType was created and stored
        assert 1 in game_state.base_types
        base_type = game_state.base_types[1]

        assert isinstance(base_type, BaseType)
        assert base_type.id == 1
        assert base_type.gui_type == 0
        assert base_type.border_sq == 5
        assert base_type.vision_main_sq == 2
        assert base_type.vision_invis_sq == 3
        assert base_type.vision_subs_sq == 4

    @pytest.mark.asyncio
    async def test_handler_multiple_base_types(self):
        """Test handling multiple base type packets."""
        game_state = GameState()
        client = MockClient()

        # First base type (Fortress)
        payload1 = bytes([0x03, 0x00, 0x00])  # id=0, gui_type=0
        await handle_ruleset_base(client, game_state, payload1)

        # Second base type (Airbase)
        payload2 = bytes([0x03, 0x01, 0x01])  # id=1, gui_type=1
        await handle_ruleset_base(client, game_state, payload2)

        # Third base type (Other)
        payload3 = bytes([0x03, 0x02, 0x02])  # id=2, gui_type=2
        await handle_ruleset_base(client, game_state, payload3)

        # Verify all three are stored
        assert len(game_state.base_types) == 3
        assert game_state.base_types[0].gui_type == 0  # Fortress
        assert game_state.base_types[1].gui_type == 1  # Airbase
        assert game_state.base_types[2].gui_type == 2  # Other

    @pytest.mark.asyncio
    async def test_handler_with_cached_values(self):
        """Test handler with delta protocol caching."""
        game_state = GameState()
        client = MockClient()

        # First packet: full data
        payload1 = bytes([0x3F, 0x05, 0x01, 0x0A, 0x08, 0x06, 0x04])
        await handle_ruleset_base(client, game_state, payload1)

        # Second packet: only update border_sq (bit 2)
        payload2 = bytes([0x04, 0x14])  # border_sq=20
        await handle_ruleset_base(client, game_state, payload2)

        # Verify cached values are preserved
        base_type = game_state.base_types[5]
        assert base_type.id == 5
        assert base_type.gui_type == 1  # From first packet
        assert base_type.border_sq == 20  # Updated
        assert base_type.vision_main_sq == 8  # From first packet
        assert base_type.vision_invis_sq == 6  # From first packet
        assert base_type.vision_subs_sq == 4  # From first packet
