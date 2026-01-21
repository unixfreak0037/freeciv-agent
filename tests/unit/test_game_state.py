"""
Unit tests for GameState - FreeCiv game state tracking.

Tests the simple data class that maintains current game state as packets
are received from the server.
"""

import pytest
from fc_client.game_state import GameState


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
