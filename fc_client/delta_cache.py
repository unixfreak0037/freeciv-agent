"""Delta cache for FreeCiv protocol delta encoding."""

from typing import Dict, Tuple, Any, Optional


class DeltaCache:
    """Manages cached packet state for delta protocol.

    The delta protocol is FreeCiv's bandwidth optimization that transmits
    only changed fields using bitvectors. This cache stores previous packet
    values so that unchanged fields can be reconstructed from cache.

    Cache structure: {packet_type: {key_tuple: {field_name: value}}}
    """

    def __init__(self):
        """Initialize empty delta cache."""
        self._cache: Dict[int, Dict[Tuple, Dict[str, Any]]] = {}

    def get_cached_packet(
        self, packet_type: int, key_values: Tuple = ()
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached packet by type and key values.

        Args:
            packet_type: The packet type number (e.g., 25 for PACKET_CHAT_MSG)
            key_values: Tuple of key field values that identify this specific packet
                       For packets with no key fields, use empty tuple ()

        Returns:
            Dictionary of field values if cached, None if not found
        """
        if packet_type not in self._cache:
            return None
        return self._cache[packet_type].get(key_values)

    def update_cache(self, packet_type: int, key_values: Tuple, fields: Dict[str, Any]) -> None:
        """Update cache with new packet data.

        Args:
            packet_type: The packet type number
            key_values: Tuple of key field values
            fields: Complete dictionary of all field values for this packet
        """
        if packet_type not in self._cache:
            self._cache[packet_type] = {}
        # Store a copy to prevent external modifications
        self._cache[packet_type][key_values] = fields.copy()

    def clear_all(self) -> None:
        """Clear entire cache (should be called on disconnect)."""
        self._cache.clear()

    def clear_packet_type(self, packet_type: int) -> None:
        """Clear cache for a specific packet type.

        Args:
            packet_type: The packet type to clear
        """
        if packet_type in self._cache:
            del self._cache[packet_type]

    def __repr__(self) -> str:
        """String representation showing cache statistics."""
        total_entries = sum(len(cache) for cache in self._cache.values())
        return f"DeltaCache(packet_types={len(self._cache)}, total_entries={total_entries})"
