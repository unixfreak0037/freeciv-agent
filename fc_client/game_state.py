"""
Game state tracking for the FreeCiv client.

The GameState class maintains the current state of the game as packets
are received and processed from the server.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RulesetControl:
    """
    Ruleset configuration from PACKET_RULESET_CONTROL (packet 155).

    Contains counts of all game entities (units, techs, nations, etc.)
    and ruleset metadata. Sent during initialization.
    """
    # Entity counts (24 UINT16 fields)
    num_unit_classes: int
    num_unit_types: int
    num_impr_types: int
    num_tech_classes: int
    num_tech_types: int
    num_extra_types: int
    num_tiledef_types: int
    num_base_types: int
    num_road_types: int
    num_resource_types: int
    num_goods_types: int
    num_disaster_types: int
    num_achievement_types: int
    num_multipliers: int
    num_styles: int
    num_music_styles: int
    government_count: int
    nation_count: int
    num_city_styles: int
    terrain_count: int
    num_specialist_types: int
    num_normal_specialists: int
    num_nation_groups: int
    num_nation_sets: int

    # Client preferences (3 STRING fields + 1 BOOL)
    preferred_tileset: str
    preferred_soundset: str
    preferred_musicset: str
    popup_tech_help: bool

    # Ruleset metadata (3 STRING fields + 2 numeric)
    name: str
    version: str
    alt_dir: str
    desc_length: int  # UINT32
    num_counters: int  # UINT16


class GameState:
    """Tracks the current game state as packets are processed."""

    def __init__(self):
        """Initialize a new game state with default values."""
        self.server_info = None
        self.chat_history = []  # List of chat message dicts with timestamps
        self.ruleset_control: Optional[RulesetControl] = None  # Ruleset configuration (PACKET_RULESET_CONTROL)
