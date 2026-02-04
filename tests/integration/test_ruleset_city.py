"""
Integration tests for PACKET_RULESET_CITY (149) handler.

Tests decoder, delta protocol caching, and handler integration with GameState.
"""

import pytest
from fc_client.delta_cache import DeltaCache
from fc_client import protocol
from fc_client.game_state import GameState, CityStyle, Requirement


class TestPacketRulesetCity:
    """Tests for PACKET_RULESET_CITY (149) decoder and handler."""

    def test_decode_all_fields_present(self, delta_cache):
        """Test decoding with all bitvector bits set."""
        # Bitvector: 0xFF (all 8 bits set)
        # Build test payload with all fields
        payload = bytearray()

        # Bitvector (1 byte): all bits set
        payload.append(0xFF)

        # Bit 0: style_id (UINT8)
        payload.append(2)

        # Bit 1: name (STRING)
        name = "European"
        payload.extend(name.encode("utf-8"))
        payload.append(0)  # null terminator

        # Bit 2: rule_name (STRING)
        rule_name = "european"
        payload.extend(rule_name.encode("utf-8"))
        payload.append(0)

        # Bit 3: citizens_graphic (STRING)
        citizens_graphic = "city.european"
        payload.extend(citizens_graphic.encode("utf-8"))
        payload.append(0)

        # Bit 4: reqs_count (UINT8)
        payload.append(0)  # No requirements for this test

        # Bit 5: reqs array (empty since reqs_count = 0)

        # Bit 6: graphic (STRING)
        graphic = "city.european_modern"
        payload.extend(graphic.encode("utf-8"))
        payload.append(0)

        # Bit 7: graphic_alt (STRING)
        graphic_alt = "city.classical"
        payload.extend(graphic_alt.encode("utf-8"))
        payload.append(0)

        # Decode
        result = protocol.decode_ruleset_city(bytes(payload), delta_cache)

        # Verify all fields
        assert result["style_id"] == 2
        assert result["name"] == "European"
        assert result["rule_name"] == "european"
        assert result["citizens_graphic"] == "city.european"
        assert result["reqs_count"] == 0
        assert result["reqs"] == []
        assert result["graphic"] == "city.european_modern"
        assert result["graphic_alt"] == "city.classical"

    def test_decode_minimal_fields(self, delta_cache):
        """Test decoding with only key field (style_id)."""
        # Bitvector: 0x01 (only bit 0 set)
        payload = bytearray()

        # Bitvector
        payload.append(0x01)

        # Bit 0: style_id
        payload.append(5)

        # Decode
        result = protocol.decode_ruleset_city(bytes(payload), delta_cache)

        # Verify key field and defaults
        assert result["style_id"] == 5
        assert result["name"] == ""
        assert result["rule_name"] == ""
        assert result["citizens_graphic"] == ""
        assert result["reqs_count"] == 0
        assert result["reqs"] == []
        assert result["graphic"] == ""
        assert result["graphic_alt"] == ""

    def test_decode_with_requirements(self, delta_cache):
        """Test decoding city style with requirement array."""
        payload = bytearray()

        # Bitvector: 0x31 (bits 0, 4, 5 set - style_id, reqs_count, reqs)
        payload.append(0x31)

        # Bit 0: style_id
        payload.append(3)

        # Bit 4: reqs_count
        payload.append(2)  # 2 requirements

        # Bit 5: reqs array (2 requirements, each 10 bytes)
        # Requirement structure: type(UINT8), value(SINT32), range(UINT8), survives(BOOL8), present(BOOL8), quiet(BOOL8)
        # Requirement 1: type=1, value=10, range=2, survives=False, present=True, quiet=False
        payload.append(1)  # type (UINT8)
        payload.extend((10).to_bytes(4, byteorder="big", signed=True))  # value (SINT32, big-endian)
        payload.append(2)  # range (UINT8)
        payload.append(0)  # survives (BOOL8)
        payload.append(1)  # present (BOOL8)
        payload.append(0)  # quiet (BOOL8)

        # Requirement 2: type=5, value=20, range=3, survives=False, present=False, quiet=False
        payload.append(5)  # type
        payload.extend((20).to_bytes(4, byteorder="big", signed=True))  # value
        payload.append(3)  # range
        payload.append(0)  # survives
        payload.append(0)  # present
        payload.append(0)  # quiet

        # Decode
        result = protocol.decode_ruleset_city(bytes(payload), delta_cache)

        # Verify
        assert result["style_id"] == 3
        assert result["reqs_count"] == 2
        assert len(result["reqs"]) == 2

        # Check first requirement
        req1 = result["reqs"][0]
        assert req1["type"] == 1
        assert req1["range"] == 2
        assert req1["present"] is True
        assert req1["value"] == 10

        # Check second requirement
        req2 = result["reqs"][1]
        assert req2["type"] == 5
        assert req2["range"] == 3
        assert req2["present"] is False
        assert req2["value"] == 20

    def test_delta_protocol_caching(self, delta_cache):
        """Test delta cache updates and retrieval."""
        # First packet with all fields
        payload1 = bytearray()
        payload1.append(0xFF)  # All bits set
        payload1.append(1)  # style_id

        # Add all string fields
        for string in [
            "Classical",
            "classical",
            "city.classical",
            "city.classical_modern",
            "city.ancient",
        ]:
            payload1.extend(string.encode("utf-8"))
            payload1.append(0)

        # Add reqs_count (insert before the last two strings)
        payload1_temp = bytearray()
        payload1_temp.append(0xFF)
        payload1_temp.append(1)  # style_id

        name = "Classical"
        payload1_temp.extend(name.encode("utf-8"))
        payload1_temp.append(0)

        rule_name = "classical"
        payload1_temp.extend(rule_name.encode("utf-8"))
        payload1_temp.append(0)

        citizens = "city.classical"
        payload1_temp.extend(citizens.encode("utf-8"))
        payload1_temp.append(0)

        payload1_temp.append(0)  # reqs_count = 0

        graphic = "city.classical_modern"
        payload1_temp.extend(graphic.encode("utf-8"))
        payload1_temp.append(0)

        graphic_alt = "city.ancient"
        payload1_temp.extend(graphic_alt.encode("utf-8"))
        payload1_temp.append(0)

        result1 = protocol.decode_ruleset_city(bytes(payload1_temp), delta_cache)

        assert result1["name"] == "Classical"
        assert result1["graphic"] == "city.classical_modern"

        # Second packet with only changed fields (bits 1 and 6 - name and graphic)
        payload2 = bytearray()
        payload2.append(0x41)  # Bits 0, 6 set (style_id, graphic)
        payload2.append(1)  # Same style_id

        new_graphic = "city.classical_updated"
        payload2.extend(new_graphic.encode("utf-8"))
        payload2.append(0)

        result2 = protocol.decode_ruleset_city(bytes(payload2), delta_cache)

        # Verify cache provided missing fields
        assert result2["style_id"] == 1
        assert result2["name"] == "Classical"  # From cache
        assert result2["rule_name"] == "classical"  # From cache
        assert result2["graphic"] == "city.classical_updated"  # Updated
        assert result2["graphic_alt"] == "city.ancient"  # From cache

    def test_handler_stores_city_style(self, freeciv_client, game_state):
        """Test handler integration with GameState."""
        # Initialize game_state in the client
        freeciv_client.game_state = game_state

        # Build packet payload
        payload = bytearray()
        payload.append(0xFF)  # All bits set
        payload.append(7)  # style_id

        for string in [
            "Tropical",
            "tropical",
            "city.tropical",
            "city.tropical_modern",
            "city.classical",
        ]:
            payload.extend(string.encode("utf-8"))
            payload.append(0)

        # Rebuild with proper order
        payload = bytearray()
        payload.append(0xFF)
        payload.append(7)

        payload.extend(b"Tropical\x00")
        payload.extend(b"tropical\x00")
        payload.extend(b"city.tropical\x00")
        payload.append(0)  # reqs_count
        payload.extend(b"city.tropical_modern\x00")
        payload.extend(b"city.classical\x00")

        # Import handler
        from fc_client.handlers.ruleset import handle_ruleset_city
        import asyncio

        # Call handler
        asyncio.run(handle_ruleset_city(freeciv_client, game_state, bytes(payload)))

        # Verify stored in game state
        assert 7 in freeciv_client.game_state.city_styles
        city_style = freeciv_client.game_state.city_styles[7]

        assert isinstance(city_style, CityStyle)
        assert city_style.style_id == 7
        assert city_style.name == "Tropical"
        assert city_style.rule_name == "tropical"
        assert city_style.citizens_graphic == "city.tropical"
        assert city_style.graphic == "city.tropical_modern"
        assert city_style.graphic_alt == "city.classical"
        assert city_style.reqs_count == 0
        assert city_style.reqs == []

    def test_handler_multiple_city_styles(self, freeciv_client, game_state):
        """Test handler with sequential style definitions."""
        # Initialize game_state in the client
        freeciv_client.game_state = game_state

        from fc_client.handlers.ruleset import handle_ruleset_city
        import asyncio

        # Define helper to create packet
        def create_packet(style_id, name, rule_name):
            payload = bytearray()
            payload.append(0x0F)  # Bits 0-3 set (style_id, name, rule_name, citizens_graphic)
            payload.append(style_id)
            payload.extend(name.encode("utf-8"))
            payload.append(0)
            payload.extend(rule_name.encode("utf-8"))
            payload.append(0)
            payload.extend(f"city.{rule_name}".encode("utf-8"))
            payload.append(0)
            return bytes(payload)

        # Send multiple city styles
        styles = [
            (0, "European", "european"),
            (1, "Classical", "classical"),
            (2, "Tropical", "tropical"),
        ]

        for style_id, name, rule_name in styles:
            packet = create_packet(style_id, name, rule_name)
            asyncio.run(handle_ruleset_city(freeciv_client, game_state, packet))

        # Verify all stored
        assert len(freeciv_client.game_state.city_styles) == 3

        for style_id, name, rule_name in styles:
            assert style_id in freeciv_client.game_state.city_styles
            city_style = freeciv_client.game_state.city_styles[style_id]
            assert city_style.name == name
            assert city_style.rule_name == rule_name
            assert city_style.citizens_graphic == f"city.{rule_name}"
