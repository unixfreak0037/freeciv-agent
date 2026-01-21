"""
Unit tests for DeltaCache - FreeCiv delta protocol cache management.

Tests the cache that stores previous packet values for bandwidth optimization.
"""

import pytest
from fc_client.delta_cache import DeltaCache


# ============================================================================
# Initialization Tests
# ============================================================================


@pytest.mark.unit
def test_delta_cache_initializes_empty():
    """Cache should start empty with no packet types stored."""
    cache = DeltaCache()

    # Cache should be empty - repr should show 0 types and entries
    repr_str = repr(cache)
    assert "packet_types=0" in repr_str
    assert "total_entries=0" in repr_str


# ============================================================================
# Basic Storage and Retrieval
# ============================================================================


@pytest.mark.unit
def test_cache_stores_and_retrieves_single_packet(delta_cache):
    """Should store and retrieve a single packet correctly."""
    # Store packet data
    delta_cache.update_cache(25, (0,), {"turn": 42, "year": 1850})

    # Retrieve same packet
    cached = delta_cache.get_cached_packet(25, (0,))
    assert cached == {"turn": 42, "year": 1850}


@pytest.mark.unit
def test_cache_miss_returns_none(delta_cache):
    """Should return None when requesting uncached packet."""
    result = delta_cache.get_cached_packet(25, (999,))
    assert result is None


@pytest.mark.unit
def test_cache_miss_unknown_packet_type(delta_cache):
    """Should return None for unknown packet types."""
    # Store packet type 25
    delta_cache.update_cache(25, (0,), {"turn": 1})

    # Request different packet type
    result = delta_cache.get_cached_packet(99, (0,))
    assert result is None


@pytest.mark.unit
def test_cache_updates_existing_entry(delta_cache):
    """Should overwrite existing cache entry with new data."""
    # Store initial data
    delta_cache.update_cache(25, (0,), {"turn": 1, "year": 1850})

    # Update with new data
    delta_cache.update_cache(25, (0,), {"turn": 2, "year": 1852})

    # Should have new values
    cached = delta_cache.get_cached_packet(25, (0,))
    assert cached["turn"] == 2
    assert cached["year"] == 1852


# ============================================================================
# Multiple Keys and Entries
# ============================================================================


@pytest.mark.unit
def test_cache_stores_multiple_keys_same_type(delta_cache):
    """Should store multiple packets of same type with different keys."""
    # Store multiple SERVER_INFO packets for different servers
    delta_cache.update_cache(25, (0,), {"server_id": 0, "turn": 10})
    delta_cache.update_cache(25, (1,), {"server_id": 1, "turn": 20})
    delta_cache.update_cache(25, (2,), {"server_id": 2, "turn": 30})

    # All should be retrievable independently
    assert delta_cache.get_cached_packet(25, (0,))["turn"] == 10
    assert delta_cache.get_cached_packet(25, (1,))["turn"] == 20
    assert delta_cache.get_cached_packet(25, (2,))["turn"] == 30


@pytest.mark.unit
def test_cache_isolates_different_packet_types(delta_cache):
    """Cache entries for different packet types should not interfere."""
    # Store same key_values for different packet types
    delta_cache.update_cache(25, (0,), {"type": "server_info", "turn": 1})
    delta_cache.update_cache(29, (0,), {"type": "chat_msg", "message": "hello"})

    # Both should be retrievable without interference
    server_info = delta_cache.get_cached_packet(25, (0,))
    chat_msg = delta_cache.get_cached_packet(29, (0,))

    assert server_info["type"] == "server_info"
    assert chat_msg["type"] == "chat_msg"


@pytest.mark.unit
def test_cache_handles_empty_key_tuple(delta_cache):
    """Should handle packets with no key fields (empty tuple)."""
    # Some packets have no key fields
    delta_cache.update_cache(30, (), {"data": "no key fields"})

    # Should be retrievable with empty tuple
    cached = delta_cache.get_cached_packet(30, ())
    assert cached["data"] == "no key fields"


@pytest.mark.unit
def test_cache_handles_multi_value_keys(delta_cache):
    """Should handle key tuples with multiple values."""
    # Some packets might have composite keys
    delta_cache.update_cache(50, (10, 20, 30), {"coord": "x,y,z"})

    # Should be retrievable with exact key tuple
    cached = delta_cache.get_cached_packet(50, (10, 20, 30))
    assert cached["coord"] == "x,y,z"

    # Different key should not match
    assert delta_cache.get_cached_packet(50, (10, 20, 99)) is None


# ============================================================================
# Cache Clearing
# ============================================================================


@pytest.mark.unit
def test_clear_all_empties_entire_cache(delta_cache):
    """clear_all() should remove all cached packets."""
    # Populate cache with multiple packets
    delta_cache.update_cache(25, (0,), {"turn": 1})
    delta_cache.update_cache(25, (1,), {"turn": 2})
    delta_cache.update_cache(29, (0,), {"message": "hi"})

    # Clear everything
    delta_cache.clear_all()

    # All should return None
    assert delta_cache.get_cached_packet(25, (0,)) is None
    assert delta_cache.get_cached_packet(25, (1,)) is None
    assert delta_cache.get_cached_packet(29, (0,)) is None

    # Repr should show empty cache
    repr_str = repr(delta_cache)
    assert "packet_types=0" in repr_str
    assert "total_entries=0" in repr_str


@pytest.mark.unit
def test_clear_packet_type_removes_only_specified_type(delta_cache):
    """clear_packet_type() should only remove specified packet type."""
    # Store multiple packet types
    delta_cache.update_cache(25, (0,), {"turn": 1})
    delta_cache.update_cache(25, (1,), {"turn": 2})
    delta_cache.update_cache(29, (0,), {"message": "hi"})

    # Clear only packet type 25
    delta_cache.clear_packet_type(25)

    # Type 25 should be gone
    assert delta_cache.get_cached_packet(25, (0,)) is None
    assert delta_cache.get_cached_packet(25, (1,)) is None

    # Type 29 should remain
    assert delta_cache.get_cached_packet(29, (0,))["message"] == "hi"


@pytest.mark.unit
def test_clear_nonexistent_packet_type_no_error(delta_cache):
    """Clearing a packet type that doesn't exist should not raise error."""
    # Cache is empty or doesn't have type 99
    delta_cache.clear_packet_type(99)  # Should not raise

    # Add some data
    delta_cache.update_cache(25, (0,), {"turn": 1})

    # Clear different type
    delta_cache.clear_packet_type(99)  # Should not raise

    # Original data should still exist
    assert delta_cache.get_cached_packet(25, (0,)) is not None


# ============================================================================
# Data Isolation (Copy Semantics)
# ============================================================================


@pytest.mark.unit
def test_cache_stores_copy_not_reference(delta_cache):
    """Cache should store a copy to prevent external modification."""
    # Create mutable dict
    original = {"turn": 1, "year": 1850}

    # Store in cache
    delta_cache.update_cache(25, (0,), original)

    # Modify original
    original["turn"] = 999

    # Cached value should be unchanged
    cached = delta_cache.get_cached_packet(25, (0,))
    assert cached["turn"] == 1


@pytest.mark.unit
def test_cache_retrieval_returns_reference(delta_cache):
    """Retrieved cache data is a reference (not a copy)."""
    # Store data
    delta_cache.update_cache(25, (0,), {"turn": 1})

    # Get reference
    cached1 = delta_cache.get_cached_packet(25, (0,))
    cached2 = delta_cache.get_cached_packet(25, (0,))

    # Both should reference same object
    assert cached1 is cached2

    # Modifying one affects the other (same object)
    cached1["turn"] = 999
    assert cached2["turn"] == 999


# ============================================================================
# Repr and Statistics
# ============================================================================


@pytest.mark.unit
def test_repr_shows_correct_statistics(delta_cache):
    """__repr__ should show accurate packet_types and total_entries count."""
    # Add entries
    delta_cache.update_cache(25, (0,), {"turn": 1})
    delta_cache.update_cache(25, (1,), {"turn": 2})
    delta_cache.update_cache(29, (0,), {"message": "hi"})

    repr_str = repr(delta_cache)

    # Should show 2 packet types
    assert "packet_types=2" in repr_str

    # Should show 3 total entries
    assert "total_entries=3" in repr_str


@pytest.mark.unit
def test_repr_format(delta_cache):
    """__repr__ should have expected format."""
    repr_str = repr(delta_cache)

    # Should match format: DeltaCache(packet_types=N, total_entries=M)
    assert repr_str.startswith("DeltaCache(")
    assert repr_str.endswith(")")
    assert "packet_types=" in repr_str
    assert "total_entries=" in repr_str


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.unit
def test_cache_with_complex_field_values(delta_cache):
    """Cache should handle various Python data types in fields."""
    # Test different data types
    complex_data = {
        "int": 42,
        "float": 3.14,
        "str": "hello",
        "bool": True,
        "list": [1, 2, 3],
        "dict": {"nested": "value"},
        "none": None,
    }

    delta_cache.update_cache(99, (0,), complex_data)

    cached = delta_cache.get_cached_packet(99, (0,))
    assert cached == complex_data


@pytest.mark.unit
def test_cache_with_zero_key_value(delta_cache):
    """Cache should handle key_values containing zero."""
    # Zero is a valid key value (not falsy in this context)
    delta_cache.update_cache(25, (0,), {"data": "zero key"})

    cached = delta_cache.get_cached_packet(25, (0,))
    assert cached["data"] == "zero key"
