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
class Resource:
    """Resource type from PACKET_RULESET_RESOURCE (177).

    Resources provide bonuses to tile outputs.
    Output array indices: [FOOD, SHIELD, TRADE, GOLD, LUXURY, SCIENCE]
    """
    id: int
    output: List[int]  # Length O_LAST=6


@dataclass
class Specialist:
    """Specialist type definition from PACKET_RULESET_SPECIALIST (142).

    Specialists are special city occupations (e.g., scientists, entertainers,
    taxmen) that provide bonuses to cities instead of working terrain tiles.
    """
    id: int                    # Specialist type ID
    plural_name: str           # Display name (plural form)
    rule_name: str             # Internal rule identifier
    short_name: str            # Abbreviated display name
    graphic_str: str           # Primary graphic tag
    graphic_alt: str           # Alternate graphic tag
    reqs_count: int            # Number of requirements
    reqs: List[Requirement]    # Requirements for specialist availability
    helptext: str              # Help text description


@dataclass
class Goods:
    """Goods type from PACKET_RULESET_GOODS (248).

    Goods represent tradeable commodities transported between cities
    via trade routes, generating economic bonuses.
    """
    id: int                       # Goods type ID (key)
    name: str                     # Display name
    rule_name: str                # Internal identifier
    reqs_count: int               # Number of requirements
    reqs: List[Requirement]       # Requirements for goods availability
    from_pct: int                 # Trade income % for source (0-65535)
    to_pct: int                   # Trade income % for destination (0-65535)
    onetime_pct: int              # One-time bonus % (0-65535)
    flags: int                    # Bitvector: bit0=Bidirectional, bit1=Depletes, bit2=Self-Provided
    helptext: str                 # Help text description


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
class ExtraFlag:
    """
    Extra flag from PACKET_RULESET_EXTRA_FLAG (packet 226).

    Extra flags are properties that can be assigned to extras (terrain features
    like forests, rivers, bases) in the ruleset to define game mechanics.

    Examples: ParadropFrom, ParadropTo, NoStackDeath, etc.
    """
    id: int           # Extra flag identifier
    name: str         # Flag name (MAX_LEN_NAME)
    helptxt: str      # Help text describing the flag's effect (MAX_LEN_PACKET)


@dataclass
class TerrainFlag:
    """Terrain flag from PACKET_RULESET_TERRAIN_FLAG (231).

    Terrain flags are properties that can be assigned to terrain types
    in the ruleset to define game mechanics and requirements.

    Examples: NoBarbs, NoCities, UnsafeCoast, NoFortify, etc.
    """
    id: int           # Terrain flag identifier (UINT8)
    name: str         # Flag name (MAX_LEN_NAME)
    helptxt: str      # Help text describing the flag's effect (MAX_LEN_PACKET)


@dataclass
class ImprFlag:
    """Improvement flag from PACKET_RULESET_IMPR_FLAG (20).

    Improvement flags are properties that can be assigned to improvements
    (buildings/city improvements) in the ruleset to define game mechanics.
    """
    id: int           # Improvement flag identifier (UINT8)
    name: str         # Flag name (MAX_LEN_NAME)
    helptxt: str      # Help text describing the flag's effect (MAX_LEN_PACKET)


@dataclass
class Building:
    """Building/improvement type from PACKET_RULESET_BUILDING (150).

    Buildings (also called improvements) are structures that can be built
    in cities, including Great Wonders, Small Wonders, and regular city
    improvements (libraries, temples, walls, etc.).
    """
    id: int                           # Building type ID (key)
    genus: int                        # Building genus: 0=GreatWonder, 1=SmallWonder, 2=Improvement
    name: str                         # Display name
    rule_name: str                    # Internal identifier
    graphic_str: str                  # Primary graphics tag
    graphic_alt: str                  # Alternative graphics tag
    graphic_alt2: str                 # Second alternative graphics tag
    reqs_count: int                   # Number of build requirements
    reqs: List['Requirement']         # Requirements to build
    obs_count: int                    # Number of obsolescence requirements
    obs_reqs: List['Requirement']     # Requirements that obsolete this building
    build_cost: int                   # Production cost to build
    upkeep: int                       # Gold upkeep per turn
    sabotage: int                     # Sabotage vulnerability
    flags: int                        # Bitvector of improvement flags (BV_IMPR_FLAGS)
    soundtag: str                     # Primary sound tag
    soundtag_alt: str                 # Alternative sound tag
    soundtag_alt2: str                # Second alternative sound tag
    helptext: str                     # Help text description


@dataclass
class ExtraType:
    """
    Extra type from PACKET_RULESET_EXTRA (232).

    Extras are terrain features like forests, rivers, roads, bases, and other
    map improvements. This packet defines the properties and behavior of each
    extra type in the ruleset.
    """
    # Identity
    id: int
    name: str
    rule_name: str
    category: int

    # Causes/removal (bitvectors)
    causes: int                    # BV_CAUSES (2 bytes)
    rmcauses: int                  # BV_RMCAUSES (1 byte)

    # Graphics (8 STRING fields)
    activity_gfx: str
    act_gfx_alt: str
    act_gfx_alt2: str
    rmact_gfx: str
    rmact_gfx_alt: str
    rmact_gfx_alt2: str
    graphic_str: str
    graphic_alt: str

    # Build requirements
    reqs_count: int
    reqs: List['Requirement']

    # Removal requirements
    rmreqs_count: int
    rmreqs: List['Requirement']

    # Appearance
    appearance_chance: int
    appearance_reqs_count: int
    appearance_reqs: List['Requirement']

    # Disappearance
    disappearance_chance: int
    disappearance_reqs_count: int
    disappearance_reqs: List['Requirement']

    # Visibility
    visibility_req: int            # UINT16 - tech ID

    # Booleans (header folding)
    buildable: bool
    generated: bool

    # Build/removal times
    build_time: int
    build_time_factor: int
    removal_time: int
    removal_time_factor: int

    # Combat/infrastructure
    infracost: int
    defense_bonus: int
    eus: int                       # UINT8 - extra_unit_seen_type

    # Bitvector properties
    native_to: int                 # BV_UNIT_CLASSES (4 bytes)
    flags: int                     # BV_EXTRA_FLAGS (3 bytes)
    hidden_by: int                 # BV_EXTRAS (32 bytes)
    bridged_over: int              # BV_EXTRAS (32 bytes)
    conflicts: int                 # BV_EXTRAS (32 bytes)

    # No aggression
    no_aggr_near_city: int         # SINT8

    # Help text
    helptext: str


@dataclass
class UnitClassFlag:
    """Unit class flag from PACKET_RULESET_UNIT_CLASS_FLAG (230).

    Unit class flags are properties that can be assigned to unit classes
    in the ruleset to define game mechanics and requirements.
    """
    id: int           # Unit class flag ID (key)
    name: str         # Flag name
    helptxt: str      # Help text describing the flag


@dataclass
class UnitFlag:
    """Unit flag from PACKET_RULESET_UNIT_FLAG (229).

    Unit flags are properties that can be assigned to units
    in the ruleset to define game mechanics and requirements.
    """
    id: int           # Unit flag ID
    name: str         # Flag name
    helptxt: str      # Help text describing the flag


@dataclass
class UnitBonus:
    """
    Represents a unit combat bonus from PACKET_RULESET_UNIT_BONUS (packet 228).

    Defines conditional combat bonuses that units receive when fighting against
    enemies with specific flags. For example, Pikemen might get +50% defense
    against Mounted units.
    """
    unit: int           # Unit type ID (uint16)
    flag: int           # Unit type flag ID (uint8)
    type: int           # Combat bonus type enum (uint8): 0=DefenseMultiplier, etc.
    value: int          # Bonus value (sint16, signed)
    quiet: bool         # If true, don't show bonus in UI help text


@dataclass
class UnitClass:
    """Unit class from PACKET_RULESET_UNIT_CLASS (152).

    Unit classes define categories of military units (e.g., Land, Sea, Air)
    with shared movement and combat properties.
    """
    id: int                      # Unit class ID
    name: str                    # Display name
    rule_name: str               # Internal identifier
    min_speed: int               # Minimum movement speed (UINT32)
    hp_loss_pct: int             # HP loss percentage (0-100)
    non_native_def_pct: int      # Defense penalty on non-native terrain (0-65535)
    flags: int                   # Bitvector of unit class flags (32 bits)
    helptext: str                # Descriptive help text


@dataclass
class BaseType:
    """Base type from PACKET_RULESET_BASE (153).

    Base types define military installations (forts, airbases, radar towers)
    that can be built on terrain tiles.
    """
    id: int                    # Base type ID
    gui_type: int              # GUI type: 0=Fortress, 1=Airbase, 2=Other
    border_sq: int             # Territory border expansion (squared)
    vision_main_sq: int        # Vision radius for normal units (squared)
    vision_invis_sq: int       # Vision radius for invisible units (squared)
    vision_subs_sq: int        # Vision radius for submarines (squared)


@dataclass
class RoadType:
    """Road type from PACKET_RULESET_ROAD (220).

    Defines transportation infrastructure (roads, railroads, rivers, maglev)
    that can be built on tiles, affecting movement costs and tile outputs.
    """
    id: int                          # Road type identifier
    gui_type: int                    # GUI type: 0=Road, 1=Railroad, 2=Maglev, 3=Other
    first_reqs_count: int            # Number of build requirements
    first_reqs: List[Requirement]    # Requirements to build this road
    move_cost: int                   # Movement cost (-1 = no effect)
    move_mode: int                   # 0=Cardinal, 1=Relaxed, 2=FastAlways
    tile_incr_const: List[int]       # Constant tile output increment [Food, Shield, Trade, Gold, Luxury, Science]
    tile_incr: List[int]             # Percentage tile output increment [O_LAST=6]
    tile_bonus: List[int]            # Tile output bonus [O_LAST=6]
    compat: int                      # Compatibility: 0=Road, 1=Railroad, 2=River, 3=None
    integrates: int                  # Bitvector (250 bits) of extras this integrates with
    flags: int                       # Bitvector (4 bits) of road flags


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


@dataclass
class TerrainControl:
    """Terrain control settings from PACKET_RULESET_TERRAIN_CONTROL (146)."""
    ocean_reclaim_requirement_pct: int      # Percentage requirement for ocean reclaim
    land_channel_requirement_pct: int       # Percentage requirement for land channel
    terrain_thaw_requirement_pct: int       # Percentage requirement for terrain thaw
    terrain_freeze_requirement_pct: int     # Percentage requirement for terrain freeze
    lake_max_size: int                      # Maximum lake size threshold
    min_start_native_area: int              # Minimum native area for start position
    move_fragments: int                     # Movement fragments per move
    igter_cost: int                         # Ignore terrain cost value
    pythagorean_diagonal: bool              # Use pythagorean distance for diagonals
    infrapoints: bool                       # Infrastructure points enabled
    gui_type_base0: str                     # GUI type base 0 name
    gui_type_base1: str                     # GUI type base 1 name


@dataclass
class GovernmentRulerTitle:
    """Ruler title for government/nation combination from PACKET_RULESET_GOVERNMENT_RULER_TITLE (143)."""
    gov: int            # Government type ID
    nation: int         # Nation type ID
    male_title: str     # Male ruler title (e.g., "King", "Emperor")
    female_title: str   # Female ruler title (e.g., "Queen", "Empress")


@dataclass
class UnitType:
    """Unit type from PACKET_RULESET_UNIT (140)."""
    # Identity
    id: int
    name: str
    rule_name: str

    # Graphics and sound
    graphic_str: str
    graphic_alt: str
    graphic_alt2: str
    sound_move: str
    sound_move_alt: str
    sound_fight: str
    sound_fight_alt: str

    # Classification and costs
    unit_class_id: int
    build_cost: int
    pop_cost: int
    happy_cost: int
    upkeep: List[int]  # Length O_LAST (6): FOOD, SHIELD, TRADE, GOLD, LUXURY, SCIENCE

    # Combat stats
    attack_strength: int
    defense_strength: int
    firepower: int
    hp: int

    # Movement
    move_rate: int
    fuel: int

    # Requirements
    build_reqs_count: int
    build_reqs: List[Requirement]

    # Vision and transport
    vision_radius_sq: int
    transport_capacity: int
    cargo: int  # Bitvector (BV_UNIT_CLASSES)
    embarks: int  # Bitvector (BV_UNIT_CLASSES)
    disembarks: int  # Bitvector (BV_UNIT_CLASSES)

    # Obsolescence/conversion
    obsoleted_by: int
    converted_to: int
    convert_time: int

    # Special abilities
    bombard_rate: int
    paratroopers_range: int
    city_size: int
    city_slots: int

    # Combat/vision
    tp_defense: int  # Enum (transp_def_type)
    targets: int  # Bitvector (BV_UNIT_CLASSES)
    vlayer: int  # Enum (vision_layer)

    # Veteran system
    veteran_levels: int
    veteran_name: List[str]
    power_fact: List[int]  # UINT16
    move_bonus: List[int]  # UINT32
    base_raise_chance: List[int]  # UINT8
    work_raise_chance: List[int]  # UINT8

    # Flags and abilities
    flags: int  # Bitvector (BV_UTYPE_FLAGS)
    roles: int  # Bitvector (BV_UTYPE_ROLES)
    worker: bool

    # Help text
    helptext: str


@dataclass
class Terrain:
    """Terrain type from PACKET_RULESET_TERRAIN (151)."""
    # Identity
    id: int
    tclass: int
    name: str
    rule_name: str

    # Flags (bitvectors)
    flags: int          # BV_TERRAIN_FLAGS (20 bits, 3 bytes)
    native_to: int      # BV_UNIT_CLASSES (32 bits, 4 bytes)

    # Graphics
    graphic_str: str
    graphic_alt: str
    graphic_alt2: str

    # Movement and combat
    movement_cost: int  # UINT16
    defense_bonus: int  # SINT16, can be negative

    # Production (6 outputs: FOOD, SHIELD, TRADE, GOLD, LUXURY, SCIENCE)
    output: List[int]  # Length O_LAST (6), each UINT8

    # Resources
    num_resources: int
    resources: List[int]      # Resource IDs (UINT8), length num_resources
    resource_freq: List[int]  # UINT8, length num_resources

    # Road/base improvements
    road_output_incr_pct: List[int]  # Length O_LAST (6), each UINT16
    base_time: int
    road_time: int

    # Terrain transformations
    cultivate_result: int   # Terrain_type_id
    cultivate_time: int
    plant_result: int       # Terrain_type_id
    plant_time: int
    irrigation_food_incr: int
    irrigation_time: int
    mining_shield_incr: int
    mining_time: int
    animal: int             # SINT16, -1 for none
    transform_result: int   # Terrain_type_id
    transform_time: int
    placing_time: int
    pillage_time: int

    # Extras
    extra_count: int
    extra_removal_times: List[int]  # UINT8, length extra_count

    # Appearance
    color_red: int
    color_green: int
    color_blue: int

    # Help
    helptext: str


class GameState:
    """Tracks the current game state as packets are processed."""

    def __init__(self):
        """Initialize a new game state with default values."""
        self.server_info = None
        self.game_info: Optional[Dict[str, Any]] = None  # Game state information (PACKET_GAME_INFO)
        self.chat_history = []  # List of chat message dicts with timestamps
        self.ruleset_control: Optional[RulesetControl] = None  # Ruleset configuration (PACKET_RULESET_CONTROL)
        self.terrain_control: Optional[TerrainControl] = None  # Terrain control settings (PACKET_RULESET_TERRAIN_CONTROL)
        self.terrains: Dict[int, Terrain] = {}  # Terrain types by ID (PACKET_RULESET_TERRAIN)
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
        self.resources: Dict[int, Resource] = {}  # Resources by ID (PACKET_RULESET_RESOURCE)
        self.achievements: Dict[int, AchievementType] = {}  # Achievements by ID (PACKET_RULESET_ACHIEVEMENT)
        self.specialists: Dict[int, Specialist] = {}  # Specialists by ID (PACKET_RULESET_SPECIALIST)
        self.goods: Dict[int, Goods] = {}  # Goods by ID (PACKET_RULESET_GOODS)
        self.actions: Dict[int, ActionType] = {}  # Actions by ID (PACKET_RULESET_ACTION)
        self.action_enablers: List[ActionEnabler] = []  # Action enablers (PACKET_RULESET_ACTION_ENABLER)
        self.action_auto_performers: List[ActionAutoPerformer] = []  # Auto action configs (PACKET_RULESET_ACTION_AUTO)
        self.tech_flags: Dict[int, TechFlag] = {}  # Technology flags by ID (PACKET_RULESET_TECH_FLAG)
        self.extra_flags: Dict[int, ExtraFlag] = {}  # Extra flags by ID (PACKET_RULESET_EXTRA_FLAG)
        self.extras: Dict[int, ExtraType] = {}  # Extras by ID (PACKET_RULESET_EXTRA)
        self.unit_class_flags: Dict[int, UnitClassFlag] = {}  # Unit class flags by ID (PACKET_RULESET_UNIT_CLASS_FLAG)
        self.unit_flags: Dict[int, UnitFlag] = {}  # Unit flags by ID (PACKET_RULESET_UNIT_FLAG)
        self.unit_bonuses: List[UnitBonus] = []  # Combat bonuses by unit/flag combinations (PACKET_RULESET_UNIT_BONUS)
        self.unit_classes: Dict[int, UnitClass] = {}  # Unit classes by ID (PACKET_RULESET_UNIT_CLASS)
        self.base_types: Dict[int, BaseType] = {}  # Base types by ID (PACKET_RULESET_BASE)
        self.road_types: Dict[int, RoadType] = {}  # Road types by ID (PACKET_RULESET_ROAD)
        self.techs: Dict[int, Tech] = {}  # Technologies by ID (PACKET_RULESET_TECH)
        self.governments: Dict[int, Government] = {}  # Governments by ID (PACKET_RULESET_GOVERNMENT)
        self.government_ruler_titles: List[GovernmentRulerTitle] = []  # Ruler titles (PACKET_RULESET_GOVERNMENT_RULER_TITLE)
        self.unit_types: Dict[int, UnitType] = {}  # Unit types by ID (PACKET_RULESET_UNIT)
        self.terrain_flags: Dict[int, TerrainFlag] = {}  # Terrain flags by ID (PACKET_RULESET_TERRAIN_FLAG)
        self.improvement_flags: Dict[int, ImprFlag] = {}  # Improvement flags by ID (PACKET_RULESET_IMPR_FLAG)
        self.buildings: Dict[int, Building] = {}  # Buildings/improvements by ID (PACKET_RULESET_BUILDING)
