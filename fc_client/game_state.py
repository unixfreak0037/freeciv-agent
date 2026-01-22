"""
Game state tracking for the FreeCiv client.

The GameState class maintains the current state of the game as packets
are received and processed from the server.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict


@dataclass
class RulesetControl:
    """
    Ruleset configuration from PACKET_RULESET_CONTROL (packet 155).

    Contains counts of all game entities (units, techs, nations, etc.)
    and ruleset metadata. Sent during initialization.
    """
    # Entity counts (22 UINT16 fields)
    num_unit_classes: int
    num_unit_types: int
    num_impr_types: int
    num_tech_classes: int
    num_tech_types: int
    num_extra_types: int
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


@dataclass
class NationSet:
    """
    Represents a nation set from PACKET_RULESET_NATION_SETS (packet 236).

    A nation set is a collection of nations grouped by theme, era, or region.
    Examples: "Core", "Extended", "Custom"
    """
    name: str          # Display name (MAX_LEN_NAME = 48 bytes)
    rule_name: str     # Internal identifier (MAX_LEN_NAME = 48 bytes)
    description: str   # Descriptive text (MAX_LEN_MSG = 1536 bytes)


@dataclass
class NationGroup:
    """
    Represents a nation group from PACKET_RULESET_NATION_GROUPS (packet 147).

    A nation group is a category of nations, such as "Ancient", "Medieval",
    "African", "European", etc. Groups can be hidden from player selection.
    """
    name: str      # Display name (MAX_LEN_NAME = 48 bytes)
    hidden: bool   # Whether the group is hidden from player selection


@dataclass
class Nation:
    """
    Represents a nation/civilization from PACKET_RULESET_NATION (packet 148).

    Contains detailed information about a playable or AI nation, including
    leaders, starting conditions, and associated sets/groups.
    """
    id: int                           # Nation ID (key field)
    translation_domain: str           # Translation domain for i18n
    adjective: str                    # Adjective form (e.g., "Roman")
    rule_name: str                    # Internal identifier
    noun_plural: str                  # Plural form (e.g., "Romans")
    graphic_str: str                  # Primary graphics tag
    graphic_alt: str                  # Alternative graphics tag
    legend: str                       # Descriptive text/legend
    style: int                        # Nation style ID
    leader_count: int                 # Number of leaders
    leader_name: List[str]            # Leader names
    leader_is_male: List[bool]        # Leader genders (True=male)
    is_playable: bool                 # Whether human players can select this nation
    barbarian_type: int               # Barbarian type (0=not barbarian)
    nsets: int                        # Number of nation sets
    sets: List[int]                   # Nation set IDs
    ngroups: int                      # Number of nation groups
    groups: List[int]                 # Nation group IDs
    init_government_id: int           # Starting government (-1=none)
    init_techs_count: int             # Number of starting techs
    init_techs: List[int]             # Starting technology IDs
    init_units_count: int             # Number of starting units
    init_units: List[int]             # Starting unit type IDs
    init_buildings_count: int         # Number of starting buildings
    init_buildings: List[int]         # Starting building/improvement IDs


class GameState:
    """Tracks the current game state as packets are processed."""

    def __init__(self):
        """Initialize a new game state with default values."""
        self.server_info = None
        self.chat_history = []  # List of chat message dicts with timestamps
        self.ruleset_control: Optional[RulesetControl] = None  # Ruleset configuration (PACKET_RULESET_CONTROL)
        self.ruleset_summary: Optional[str] = None  # Ruleset summary text (PACKET_RULESET_SUMMARY)
        self.ruleset_description_parts: List[str] = []  # Accumulator for description chunks
        self.ruleset_description: Optional[str] = None  # Complete assembled description
        self.nation_sets: List[NationSet] = []  # Available nation sets (PACKET_RULESET_NATION_SETS)
        self.nation_groups: List[NationGroup] = []  # Available nation groups (PACKET_RULESET_NATION_GROUPS)
        self.nations: Dict[int, Nation] = {}  # Nations by ID (PACKET_RULESET_NATION)
