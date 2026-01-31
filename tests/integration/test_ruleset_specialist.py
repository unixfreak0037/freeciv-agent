"""Tests for PACKET_RULESET_SPECIALIST (142) handler."""

import pytest
from fc_client.game_state import GameState, Specialist
from fc_client import protocol
from fc_client.delta_cache import DeltaCache
from fc_client.handlers import ruleset
from unittest.mock import AsyncMock, MagicMock


def test_decode_ruleset_specialist_entertainers():
    """Test decoding real captured specialist packet (Entertainers)."""
    # Load captured packet data (includes header: 2 bytes length + 2 bytes type)
    with open("packets/inbound_2305_type142.packet", "rb") as f:
        raw_packet = f.read()

    # Strip header (2 bytes length + 2 bytes type = 4 bytes total)
    payload = raw_packet[4:]

    # Decode
    delta_cache = DeltaCache()
    data = protocol.decode_ruleset_specialist(payload, delta_cache)

    # Verify specialist data
    # NOTE: This is packet #2305, late in the sequence. Bit 0 (id) is NOT set,
    # so ID defaults to 0 from cache/initialization. The actual specialist ID
    # would come from earlier packets or game context.
    assert data["id"] == 0  # Defaults to 0 because bit 0 not set in bitvector
    assert data["plural_name"] == "Entertainers"
    assert data["rule_name"] == "elvis"
    assert "?" in data["short_name"] or "Elvis" in data["short_name"]
    assert data["graphic_str"] == "specialist.entertainer"
    assert data["graphic_alt"] in ["-", ""]
    assert "luxury" in data["helptext"].lower()


def test_decode_ruleset_specialist_delta_protocol():
    """Test delta protocol caching for specialist packets."""
    # First packet (full data) - strip header
    with open("packets/inbound_2305_type142.packet", "rb") as f:
        raw_packet = f.read()
    payload1 = raw_packet[4:]

    delta_cache = DeltaCache()
    data1 = protocol.decode_ruleset_specialist(payload1, delta_cache)

    # Verify data is cached
    # DeltaCache stores by packet_type as key, with () tuple as subkey
    assert protocol.PACKET_RULESET_SPECIALIST in delta_cache._cache
    packet_cache = delta_cache._cache[protocol.PACKET_RULESET_SPECIALIST]
    assert () in packet_cache
    cached_data = packet_cache[()]
    assert cached_data["id"] == data1["id"]
    assert cached_data["plural_name"] == data1["plural_name"]


@pytest.mark.asyncio
async def test_handle_ruleset_specialist():
    """Test specialist handler updates game state correctly."""
    # Load captured packet - strip header
    with open("packets/inbound_2305_type142.packet", "rb") as f:
        raw_packet = f.read()
    payload = raw_packet[4:]

    # Create mock client and game state
    client = MagicMock()
    client._delta_cache = DeltaCache()
    game_state = GameState()

    # Call handler
    await ruleset.handle_ruleset_specialist(client, game_state, payload)

    # Verify game state was updated
    # NOTE: ID is 0 because bit 0 not set in this captured packet
    assert 0 in game_state.specialists
    specialist = game_state.specialists[0]

    assert isinstance(specialist, Specialist)
    assert specialist.id == 0
    assert specialist.plural_name == "Entertainers"
    assert specialist.rule_name == "elvis"
    assert specialist.graphic_str == "specialist.entertainer"
    assert isinstance(specialist.reqs, list)
    assert "luxury" in specialist.helptext.lower()


def test_specialist_dataclass():
    """Test Specialist dataclass creation."""
    specialist = Specialist(
        id=1,
        plural_name="Scientists",
        rule_name="scientist",
        short_name="?Sci",
        graphic_str="specialist.scientist",
        graphic_alt="-",
        reqs_count=0,
        reqs=[],
        helptext="Scientists produce research.",
    )

    assert specialist.id == 1
    assert specialist.plural_name == "Scientists"
    assert specialist.rule_name == "scientist"
    assert specialist.reqs_count == 0
    assert len(specialist.reqs) == 0


def test_decode_specialist_with_requirements():
    """Test decoding specialist packet with requirements (if captured)."""
    # This test would need a captured packet with requirements
    # For now, we test the structure is correct for zero requirements
    with open("packets/inbound_2305_type142.packet", "rb") as f:
        raw_packet = f.read()
    payload = raw_packet[4:]

    delta_cache = DeltaCache()
    data = protocol.decode_ruleset_specialist(payload, delta_cache)

    # Verify requirements handling
    assert "reqs_count" in data
    assert "reqs" in data
    assert isinstance(data["reqs"], list)
    assert len(data["reqs"]) == data["reqs_count"]
