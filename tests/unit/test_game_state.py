"""
Unit tests for GameState - FreeCiv game state tracking.

Tests the simple data class that maintains current game state as packets
are received from the server.
"""

import pytest
from fc_client.game_state import GameState, RulesetControl

# ============================================================================
# Initialization Tests
# ============================================================================


@pytest.mark.unit
def test_game_state_initializes_with_defaults():
    """GameState should initialize with server_info=None and empty chat_history."""
    state = GameState()

    assert state.server_info is None
    assert state.chat_history == []


@pytest.mark.unit
def test_game_state_fixture_provides_fresh_instance(game_state):
    """Fixture should provide a fresh GameState with default values."""
    assert game_state.server_info is None
    assert game_state.chat_history == []


# ============================================================================
# Server Info Tests
# ============================================================================


@pytest.mark.unit
def test_game_state_can_set_server_info(game_state):
    """Should be able to set server_info to a dict."""
    server_info = {"turn": 42, "year": 1850, "phase": 0}
    game_state.server_info = server_info

    assert game_state.server_info == server_info


@pytest.mark.unit
def test_game_state_server_info_is_mutable(game_state):
    """server_info dict should be mutable after assignment."""
    game_state.server_info = {"turn": 1}

    # Mutate the dict
    game_state.server_info["turn"] = 2
    game_state.server_info["year"] = 1850

    assert game_state.server_info["turn"] == 2
    assert game_state.server_info["year"] == 1850


@pytest.mark.unit
def test_game_state_server_info_can_be_replaced(game_state):
    """Should be able to replace server_info with new dict."""
    game_state.server_info = {"turn": 1, "year": 1850}

    # Replace with new dict
    game_state.server_info = {"turn": 2, "year": 1852}

    assert game_state.server_info["turn"] == 2
    assert game_state.server_info["year"] == 1852


# ============================================================================
# Chat History Tests
# ============================================================================


@pytest.mark.unit
def test_game_state_can_append_to_chat_history(game_state):
    """Should be able to append chat messages to history."""
    msg1 = {"message": "Welcome!", "conn_id": -1, "timestamp": 0}
    msg2 = {"message": "Hello", "conn_id": 1, "timestamp": 1}

    game_state.chat_history.append(msg1)
    game_state.chat_history.append(msg2)

    assert len(game_state.chat_history) == 2
    assert game_state.chat_history[0] == msg1
    assert game_state.chat_history[1] == msg2


@pytest.mark.unit
def test_game_state_chat_history_preserves_order(game_state):
    """chat_history should preserve chronological order."""
    # Append multiple messages
    for i in range(5):
        game_state.chat_history.append({"id": i, "message": f"msg{i}"})

    # Should be in order
    for i, msg in enumerate(game_state.chat_history):
        assert msg["id"] == i


@pytest.mark.unit
def test_game_state_chat_history_is_persistent_list(game_state):
    """chat_history should be a persistent list across accesses."""
    # Add message
    game_state.chat_history.append({"message": "first"})

    # Get reference
    history = game_state.chat_history

    # Add via attribute
    game_state.chat_history.append({"message": "second"})

    # Original reference should see both
    assert len(history) == 2
    assert history is game_state.chat_history


# ============================================================================
# Independence Tests
# ============================================================================


@pytest.mark.unit
def test_game_state_attributes_are_independent(game_state):
    """server_info and chat_history should not affect each other."""
    # Set server_info
    game_state.server_info = {"turn": 1}

    # Add chat message
    game_state.chat_history.append({"message": "hello"})

    # Both should exist independently
    assert game_state.server_info["turn"] == 1
    assert len(game_state.chat_history) == 1

    # Clearing one doesn't affect the other
    game_state.server_info = None
    assert game_state.server_info is None
    assert len(game_state.chat_history) == 1


@pytest.mark.unit
def test_multiple_game_states_are_independent():
    """Multiple GameState instances should not share state."""
    state1 = GameState()
    state2 = GameState()

    # Modify state1
    state1.server_info = {"turn": 1}
    state1.chat_history.append({"message": "state1"})

    # state2 should be unaffected
    assert state2.server_info is None
    assert state2.chat_history == []


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.unit
def test_game_state_handles_empty_dict_vs_none(game_state):
    """Should distinguish between None and empty dict for server_info."""
    # Initial state is None
    assert game_state.server_info is None

    # Set to empty dict
    game_state.server_info = {}
    assert game_state.server_info == {}
    assert game_state.server_info is not None

    # Set back to None
    game_state.server_info = None
    assert game_state.server_info is None


@pytest.mark.unit
def test_game_state_handles_large_chat_history(game_state):
    """Should handle large chat history without issues."""
    # Add many messages
    for i in range(1000):
        game_state.chat_history.append({"id": i, "message": f"msg{i}"})

    assert len(game_state.chat_history) == 1000
    assert game_state.chat_history[0]["id"] == 0
    assert game_state.chat_history[999]["id"] == 999


@pytest.mark.unit
def test_game_state_can_clear_chat_history(game_state):
    """Should be able to clear chat_history by reassigning."""
    # Add messages
    game_state.chat_history.append({"message": "msg1"})
    game_state.chat_history.append({"message": "msg2"})

    # Clear by reassigning
    game_state.chat_history = []

    assert game_state.chat_history == []


# ============================================================================
# RulesetControl Tests
# ============================================================================


@pytest.mark.unit
def test_ruleset_control_from_dict_unpacking():
    """RulesetControl should be creatable from dict unpacking (handler pattern)."""
    data = {
        "num_unit_classes": 10,
        "num_unit_types": 50,
        "num_impr_types": 40,
        "num_tech_classes": 5,
        "num_tech_types": 88,
        "num_extra_types": 20,
        "num_base_types": 8,
        "num_road_types": 6,
        "num_resource_types": 25,
        "num_goods_types": 4,
        "num_disaster_types": 7,
        "num_achievement_types": 12,
        "num_multipliers": 3,
        "num_styles": 5,
        "num_music_styles": 3,
        "government_count": 8,
        "nation_count": 200,
        "num_city_styles": 10,
        "terrain_count": 30,
        "num_specialist_types": 5,
        "num_nation_groups": 15,
        "num_nation_sets": 10,
        "preferred_tileset": "amplio2",
        "preferred_soundset": "stdmusic",
        "preferred_musicset": "stdmusic",
        "popup_tech_help": True,
        "name": "Classic",
        "version": "1.0",
        "alt_dir": "",
        "desc_length": 1024,
        "num_counters": 5,
    }

    ruleset = RulesetControl(**data)

    assert ruleset.name == "Classic"
    assert ruleset.version == "1.0"
    assert ruleset.num_unit_types == 50
    assert ruleset.popup_tech_help is True


@pytest.mark.unit
def test_ruleset_control_attribute_access():
    """RulesetControl should use attribute access, not dict access."""
    data = {
        "num_unit_classes": 10,
        "num_unit_types": 50,
        "num_impr_types": 40,
        "num_tech_classes": 5,
        "num_tech_types": 88,
        "num_extra_types": 20,
        "num_base_types": 8,
        "num_road_types": 6,
        "num_resource_types": 25,
        "num_goods_types": 4,
        "num_disaster_types": 7,
        "num_achievement_types": 12,
        "num_multipliers": 3,
        "num_styles": 5,
        "num_music_styles": 3,
        "government_count": 8,
        "nation_count": 200,
        "num_city_styles": 10,
        "terrain_count": 30,
        "num_specialist_types": 5,
        "num_nation_groups": 15,
        "num_nation_sets": 10,
        "preferred_tileset": "amplio2",
        "preferred_soundset": "stdmusic",
        "preferred_musicset": "stdmusic",
        "popup_tech_help": True,
        "name": "Classic",
        "version": "1.0",
        "alt_dir": "",
        "desc_length": 1024,
        "num_counters": 5,
    }
    ruleset = RulesetControl(**data)

    # Attribute access works
    assert ruleset.name == "Classic"

    # Dict access should fail
    with pytest.raises(TypeError):
        _ = ruleset["name"]


@pytest.mark.unit
def test_game_state_stores_ruleset_control_dataclass(game_state):
    """GameState should store RulesetControl dataclass."""
    data = {
        "num_unit_classes": 10,
        "num_unit_types": 50,
        "num_impr_types": 40,
        "num_tech_classes": 5,
        "num_tech_types": 88,
        "num_extra_types": 20,
        "num_base_types": 8,
        "num_road_types": 6,
        "num_resource_types": 25,
        "num_goods_types": 4,
        "num_disaster_types": 7,
        "num_achievement_types": 12,
        "num_multipliers": 3,
        "num_styles": 5,
        "num_music_styles": 3,
        "government_count": 8,
        "nation_count": 200,
        "num_city_styles": 10,
        "terrain_count": 30,
        "num_specialist_types": 5,
        "num_nation_groups": 15,
        "num_nation_sets": 10,
        "preferred_tileset": "amplio2",
        "preferred_soundset": "stdmusic",
        "preferred_musicset": "stdmusic",
        "popup_tech_help": True,
        "name": "Classic",
        "version": "1.0",
        "alt_dir": "",
        "desc_length": 1024,
        "num_counters": 5,
    }

    assert game_state.ruleset_control is None

    game_state.ruleset_control = RulesetControl(**data)

    assert isinstance(game_state.ruleset_control, RulesetControl)
    assert game_state.ruleset_control.name == "Classic"
