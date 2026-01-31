"""Unit tests for array-diff protocol implementation.

Tests the decode_array_diff function which handles FreeCiv's array-diff
optimization for transmitting only changed array elements.
"""

import pytest
from fc_client.protocol import decode_array_diff


class TestArrayDiffBasic:
    """Basic array-diff decoding tests."""

    def test_decode_empty_diff(self):
        """Test array-diff with no changes (immediate sentinel)."""
        # Array size 10, sentinel = 10 (no changes)
        data = bytes([10])  # Just the sentinel

        result, offset = decode_array_diff(data, 0, "BOOL", 10, cached_array=None)

        assert len(result) == 10
        assert all(v == False for v in result)  # All defaults (False for BOOL)
        assert offset == 1

    def test_decode_single_change_uint8_indices(self):
        """Test array-diff with single change using 8-bit indices."""
        # Array size 20, update index 5 to True, sentinel = 20
        data = bytes([5, 1, 20])  # index=5, value=1 (True), sentinel=20

        result, offset = decode_array_diff(data, 0, "BOOL", 20, cached_array=None)

        assert len(result) == 20
        assert result[5] == True
        assert all(result[i] == False for i in range(20) if i != 5)
        assert offset == 3

    def test_decode_multiple_changes_uint8_indices(self):
        """Test array-diff with multiple changes using 8-bit indices."""
        # Array size 50, update indices 10, 20, 30
        # Each BOOL is 1 byte: index(1) + value(1)
        data = bytes(
            [
                10,
                1,  # index=10, value=True
                20,
                1,  # index=20, value=True
                30,
                0,  # index=30, value=False
                50,  # sentinel
            ]
        )

        result, offset = decode_array_diff(data, 0, "BOOL", 50, cached_array=None)

        assert len(result) == 50
        assert result[10] == True
        assert result[20] == True
        assert result[30] == False
        assert offset == 7

    def test_decode_with_cache(self):
        """Test array-diff updating cached array."""
        # Start with cached array
        cached = [True, False, True, False, True]

        # Update indices 1 and 3, sentinel = 5
        data = bytes(
            [
                1,
                1,  # index=1, value=True (was False)
                3,
                1,  # index=3, value=True (was False)
                5,  # sentinel
            ]
        )

        result, offset = decode_array_diff(data, 0, "BOOL", 5, cached_array=cached)

        assert len(result) == 5
        assert result[0] == True  # Unchanged from cache
        assert result[1] == True  # Updated
        assert result[2] == True  # Unchanged from cache
        assert result[3] == True  # Updated
        assert result[4] == True  # Unchanged from cache
        assert offset == 5

    def test_decode_uint16_indices(self):
        """Test array-diff with 16-bit indices (array_size > 255)."""
        # Array size 300, update index 256 (requires 2 bytes)
        # Big-endian encoding: 256 = 0x0100 = bytes([1, 0])
        # Sentinel: 300 = 0x012C = bytes([1, 44])
        data = bytes(
            [
                1,
                0,  # index=256 (big-endian uint16)
                1,  # value=True (BOOL is 1 byte)
                1,
                44,  # sentinel=300 (big-endian uint16)
            ]
        )

        result, offset = decode_array_diff(data, 0, "BOOL", 300, cached_array=None)

        assert len(result) == 300
        assert result[256] == True
        assert all(result[i] == False for i in range(300) if i != 256)
        assert offset == 5


class TestArrayDiffElementTypes:
    """Test array-diff with different element types."""

    def test_decode_sint32_elements(self):
        """Test array-diff with SINT32 elements."""
        # Array size 10, update index 5 to value 42 (SINT32 = 4 bytes big-endian)
        # 42 = 0x0000002A = bytes([0, 0, 0, 42]) in big-endian
        data = bytes(
            [
                5,  # index=5 (uint8 since array_size <= 255)
                0,
                0,
                0,
                42,  # value=42 (SINT32 big-endian)
                10,  # sentinel=10 (uint8)
            ]
        )

        result, offset = decode_array_diff(data, 0, "SINT32", 10, cached_array=None)

        assert len(result) == 10
        assert result[5] == 42
        assert all(result[i] == 0 for i in range(10) if i != 5)
        assert offset == 6

    def test_decode_uint16_elements(self):
        """Test array-diff with UINT16 elements."""
        # Array size 20, update index 10 to value 1000 (UINT16 = 2 bytes big-endian)
        # 1000 = 0x03E8 = bytes([3, 232]) in big-endian
        data = bytes(
            [
                10,  # index=10 (uint8 since array_size <= 255)
                3,
                232,  # value=1000 (UINT16 big-endian)
                20,  # sentinel=20 (uint8)
            ]
        )

        result, offset = decode_array_diff(data, 0, "UINT16", 20, cached_array=None)

        assert len(result) == 20
        assert result[10] == 1000
        assert all(result[i] == 0 for i in range(20) if i != 10)
        assert offset == 4

    def test_decode_sint8_elements(self):
        """Test array-diff with SINT8 elements (e.g., PLAYER type)."""
        # Array size 15, update index 7 to value -1 (SINT8)
        # -1 as signed byte = 255 as unsigned byte = 0xFF
        data = bytes([7, 255, 15])  # index=7  # value=-1 (SINT8)  # sentinel

        result, offset = decode_array_diff(data, 0, "SINT8", 15, cached_array=None)

        assert len(result) == 15
        assert result[7] == -1
        assert all(result[i] == 0 for i in range(15) if i != 7)
        assert offset == 3


class TestArrayDiffEdgeCases:
    """Test edge cases and error conditions."""

    def test_decode_first_element(self):
        """Test updating first element (index 0)."""
        data = bytes([0, 1, 10])  # index=0, value=True  # sentinel

        result, offset = decode_array_diff(data, 0, "BOOL", 10, cached_array=None)

        assert result[0] == True
        assert len(result) == 10

    def test_decode_last_element(self):
        """Test updating last element (index = array_size - 1)."""
        data = bytes([9, 1, 10])  # index=9 (last valid index for size 10), value=True  # sentinel

        result, offset = decode_array_diff(data, 0, "BOOL", 10, cached_array=None)

        assert result[9] == True
        assert len(result) == 10

    def test_decode_invalid_index(self):
        """Test error on index exceeding array size."""
        # Index 11 exceeds array size 10 (sentinel is 10, so max valid index is 9)
        data = bytes([11, 1, 10])  # index=11 (invalid!), value=True  # sentinel

        with pytest.raises(ValueError, match="exceeds array size"):
            decode_array_diff(data, 0, "BOOL", 10, cached_array=None)

    def test_decode_all_elements_changed(self):
        """Test array-diff where all elements are updated (worst case)."""
        # Update all 5 elements
        data = bytes([0, 1, 1, 0, 2, 1, 3, 0, 4, 1, 5])  # sentinel

        result, offset = decode_array_diff(data, 0, "BOOL", 5, cached_array=None)

        assert result == [True, False, True, False, True]
        assert offset == 11

    def test_decode_with_offset(self):
        """Test decoding array-diff starting at non-zero offset."""
        # Prefix of 3 bytes, then array-diff data
        data = bytes(
            [99, 88, 77, 5, 1, 10]  # prefix (ignored)
        )  # array-diff: index=5, value=True, sentinel=10

        result, offset = decode_array_diff(data, 3, "BOOL", 10, cached_array=None)

        assert result[5] == True
        assert offset == 6  # 3 (start) + 3 (array-diff bytes)

    def test_decode_preserves_cache_unmodified_indices(self):
        """Test that unmodified indices retain cached values."""
        cached = [10, 20, 30, 40, 50]

        # Only update index 2, leave others from cache
        # 99 = 0x00000063 = bytes([0, 0, 0, 99]) in big-endian
        data = bytes(
            [
                2,  # index=2 (uint8)
                0,
                0,
                0,
                99,  # value=99 (SINT32 big-endian)
                5,  # sentinel=5 (uint8)
            ]
        )

        result, offset = decode_array_diff(data, 0, "SINT32", 5, cached_array=cached)

        assert result[0] == 10  # From cache
        assert result[1] == 20  # From cache
        assert result[2] == 99  # Updated
        assert result[3] == 40  # From cache
        assert result[4] == 50  # From cache

    def test_decode_wrong_cache_size_reinitializes(self):
        """Test that wrong-sized cache is ignored and reinitialized."""
        # Cached array has wrong size (3 instead of 5)
        cached = [1, 2, 3]

        data = bytes([2, 1, 5])  # index=2, value=True  # sentinel for size 5

        result, offset = decode_array_diff(data, 0, "BOOL", 5, cached_array=cached)

        # Should initialize fresh array with defaults, then apply diff
        assert len(result) == 5
        assert result[2] == True
        assert result[0] == False  # Default, not from wrong-sized cache
        assert result[1] == False
