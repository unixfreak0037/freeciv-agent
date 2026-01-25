"""
Game state tracking for the FreeCiv client.

The GameState class maintains the current state of the game as packets
are received and processed from the server.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


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


@dataclass
class RulesetGame:
    """
    Ruleset game configuration from PACKET_RULESET_GAME (packet 141).

    Contains core game settings including default specialist, global starting
    resources for all civilizations, and veteran system configuration.
    """
    default_specialist: int                    # Default specialist type ID
    global_init_techs_count: int              # Number of global starting techs
    global_init_techs: List[int]              # Tech IDs given to all civilizations
    global_init_buildings_count: int          # Number of global starting buildings
    global_init_buildings: List[int]          # Building IDs given to all civilizations
    veteran_levels: int                       # Number of veteran levels
    veteran_name: List[str]                   # Names for each veteran level
    power_fact: List[int]                     # Power factor for each level (UINT16)
    move_bonus: List[int]                     # Move bonus for each level (MOVEFRAGS=UINT32)
    base_raise_chance: List[int]              # Base raise chance % for each level
    work_raise_chance: List[int]              # Work raise chance % for each level
    background_red: int                       # Background color red component (0-255)
    background_green: int                     # Background color green component (0-255)
    background_blue: int                      # Background color blue component (0-255)


@dataclass
class Requirement:
    """
    Game requirement for disasters, buildings, techs, etc.

    Requirements specify conditions that must be met for game elements to be
    available or active. Used in multiple packet types including PACKET_RULESET_DISASTER.
    """
    type: int          # universals_n enum (VUT_*)
    value: int         # Integer value (meaning depends on type)
    range: int         # req_range enum
    survives: bool     # Whether destroyed sources satisfy requirement
    present: bool      # Whether requirement must be present (vs absent)
    quiet: bool        # Whether to hide from help text


@dataclass
class DisasterType:
    """
    Disaster type configuration from PACKET_RULESET_DISASTER (packet 224).

    Disasters are negative random events (fires, plagues, etc.) that can occur
    in cities when requirements are met.
    """
    id: int                    # Disaster type ID (key)
    name: str                  # Display name (variable-length, null-terminated)
    rule_name: str             # Internal identifier (variable-length, null-terminated)
    reqs_count: int            # Number of requirements
    reqs: List[Requirement]    # Requirements list
    frequency: int             # Base probability
    effects: int               # Bitvector of disaster_effect_id flags


@dataclass
class AchievementType:
    """
    Achievement type configuration from PACKET_RULESET_ACHIEVEMENT (packet 233).

    Achievements are special accomplishments players can earn during the game.

    NOTE: packets.def incorrectly lists a UINT16 'value' field that does NOT
    exist in real server packets. Verified against captured packet data.
    """
    id: int                    # Achievement type ID (key)
    name: str                  # Display name
    rule_name: str             # Internal identifier
    type: int                  # Achievement type enum (ACHIEVEMENT_TYPE)
    unique: bool               # Whether only one player can achieve this


@dataclass
class TradeRouteType:
    """Trade route type configuration from PACKET_RULESET_TRADE (227)."""
    id: int              # Trade route type ID
    trade_pct: int      # Trade percentage (0-65535)
    cancelling: int     # Illegal route handling (TRI enum)
    bonus_type: int     # Trade bonus type (TR_BONUS_TYPE enum)


@dataclass
class ActionType:
    """Action type configuration from PACKET_RULESET_ACTION (246).

    Actions define what units can do: establish embassies, create trade routes,
    spy missions, combat actions, etc. Each action has requirements, targeting
    rules, and can be blocked by other actions.
    """
    id: int                           # Action type ID (key)
    ui_name: str                      # Display name (e.g., "Establish %sEmbassy%s")
    quiet: bool                       # Whether to suppress UI notifications
    result: int                       # Action result enum (ACTRES_*)
    sub_results: int                  # Sub-results bitvector (success/failure conditions)
    actor_consuming_always: bool      # Whether actor unit is always consumed
    act_kind: int                     # Actor kind enum (0=Unit, 1=Player, 2=City, 3=Tile)
    tgt_kind: int                     # Target kind enum (0=City, 1=Unit, 2=Units, 3=Tile, 4=Extras, 5=Self)
    sub_tgt_kind: int                 # Sub-target kind enum
    min_distance: int                 # Minimum distance to target
    max_distance: int                 # Maximum distance to target (-1 = unlimited)
    blocked_by: int                   # Bitvector of blocking actions


@dataclass
class ActionEnabler:
    """Action enabler from PACKET_RULESET_ACTION_ENABLER (235).

    Action enablers define conditions for when game actions can be performed.
    Each enabler specifies requirements for the actor (unit/city/player) and
    target (recipient of action).
    """
    enabled_action: int               # Action ID this enabler applies to
    actor_reqs_count: int             # Number of actor requirements
    actor_reqs: List[Requirement]     # Requirements for the actor
    target_reqs_count: int            # Number of target requirements
    target_reqs: List[Requirement]    # Requirements for the target


@dataclass
class ActionAutoPerformer:
    """Automatic action configuration from PACKET_RULESET_ACTION_AUTO (252).

    Defines rules for automatically performing actions when specific triggers occur,
    without player input (e.g., disbanding unit on upkeep failure, auto-attack when
    moving adjacent to enemy).
    """
    id: int                           # Configuration ID
    cause: int                        # enum action_auto_perf_cause (AAPC_*)
    reqs_count: int                   # Number of requirements
    reqs: List[Requirement]           # Requirements that must be met
    alternatives_count: int           # Number of alternative actions
    alternatives: List[int]           # Alternative action IDs (tried in order)


@dataclass
class TechFlag:
    """Technology flag from PACKET_RULESET_TECH_FLAG (234).

    Technology flags are properties that can be assigned to technologies
    in the ruleset to define game mechanics and requirements.
    """
    id: int           # Technology flag ID (key)
    name: str         # Flag name
    helptxt: str      # Help text describing the flag


@dataclass
class Tech:
    """Technology from PACKET_RULESET_TECH (144).

    Technologies represent scientific advances that players can research.
    """
    id: int
    root_req: int
    research_reqs_count: int
    research_reqs: List[Requirement]
    tclass: int
    removed: bool
    flags: int  # Bitvector of tech flags
    cost: float  # Research cost (decoded from UFLOAT)
    num_reqs: int
    name: str
    rule_name: str
    helptext: str
    graphic_str: str
    graphic_alt: str


@dataclass
class Government:
    """Government type from PACKET_RULESET_GOVERNMENT (145)."""
    id: int
    reqs_count: int
    reqs: List[Requirement]
    name: str
    rule_name: str
    graphic_str: str
    graphic_alt: str
    sound_str: str
    sound_alt: str
    sound_alt2: str
    helptext: str


class GameState:
    """Tracks the current game state as packets are processed."""

    def __init__(self):
        """Initialize a new game state with default values."""
        self.server_info = None
        self.game_info: Optional[Dict[str, Any]] = None  # Game state information (PACKET_GAME_INFO)
        self.chat_history = []  # List of chat message dicts with timestamps
        self.ruleset_control: Optional[RulesetControl] = None  # Ruleset configuration (PACKET_RULESET_CONTROL)
        self.ruleset_summary: Optional[str] = None  # Ruleset summary text (PACKET_RULESET_SUMMARY)
        self.ruleset_description_parts: List[str] = []  # Accumulator for description chunks
        self.ruleset_description: Optional[str] = None  # Complete assembled description
        self.nation_sets: List[NationSet] = []  # Available nation sets (PACKET_RULESET_NATION_SETS)
        self.nation_groups: List[NationGroup] = []  # Available nation groups (PACKET_RULESET_NATION_GROUPS)
        self.nations: Dict[int, Nation] = {}  # Nations by ID (PACKET_RULESET_NATION)
        self.nation_availability: Optional[Dict[str, Any]] = None  # Nation availability tracking (PACKET_NATION_AVAILABILITY)
        self.ruleset_game: Optional[RulesetGame] = None  # Core game configuration (PACKET_RULESET_GAME)
        self.disasters: Dict[int, DisasterType] = {}  # Disasters by ID (PACKET_RULESET_DISASTER)
        self.trade_routes: Dict[int, TradeRouteType] = {}  # Trade routes by ID (PACKET_RULESET_TRADE)
        self.achievements: Dict[int, AchievementType] = {}  # Achievements by ID (PACKET_RULESET_ACHIEVEMENT)
        self.actions: Dict[int, ActionType] = {}  # Actions by ID (PACKET_RULESET_ACTION)
        self.action_enablers: List[ActionEnabler] = []  # Action enablers (PACKET_RULESET_ACTION_ENABLER)
        self.action_auto_performers: List[ActionAutoPerformer] = []  # Auto action configs (PACKET_RULESET_ACTION_AUTO)
        self.tech_flags: Dict[int, TechFlag] = {}  # Technology flags by ID (PACKET_RULESET_TECH_FLAG)
        self.techs: Dict[int, Tech] = {}  # Technologies by ID (PACKET_RULESET_TECH)
        self.governments: Dict[int, Government] = {}  # Governments by ID (PACKET_RULESET_GOVERNMENT)
