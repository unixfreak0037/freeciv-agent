"""Packet specifications for FreeCiv protocol.

This module defines the structure of FreeCiv network packets in a declarative way,
similar to the packets.def file in the FreeCiv source code. These specifications
are used by the delta protocol decoder to properly handle packets.
"""

from dataclasses import dataclass
from typing import List, Any, Dict


@dataclass
class FieldSpec:
    """Specification for a single packet field.

    Attributes:
        name: Field name (e.g., 'message', 'tile', 'event')
        type_name: FreeCiv type name ('STRING', 'SINT32', 'SINT16', 'BOOL', 'UINT32', etc.)
        is_key: True if this is a key field (always transmitted, not in bitvector)
        is_bool: True if this is a boolean field (uses header folding optimization)
        default_value: Default value to use when field is not in cache
        is_array: True if this field is an array
        array_size: Maximum array size (e.g., A_LAST, B_LAST constants)
        array_diff: True if array uses diff optimization (only changed elements transmitted)
        element_type: Element type for arrays (e.g., 'BOOL', 'SINT32', 'PLAYER')
    """
    name: str
    type_name: str
    is_key: bool = False
    is_bool: bool = False
    default_value: Any = None

    # Array-diff support
    is_array: bool = False
    array_size: int = 0
    array_diff: bool = False
    element_type: str = None

    def __post_init__(self):
        """Set default value based on type if not provided."""
        if self.default_value is None:
            if self.is_array:
                # Arrays default to empty list
                self.default_value = []
            elif self.type_name == 'STRING':
                self.default_value = ""
            elif self.type_name == 'BOOL':
                self.default_value = False
                self.is_bool = True  # Auto-detect bool fields
            elif 'SINT' in self.type_name:
                self.default_value = -1
            else:
                self.default_value = 0


@dataclass
class PacketSpec:
    """Complete specification for a packet type.

    Attributes:
        packet_type: Numeric packet type (e.g., 25 for PACKET_CHAT_MSG)
        name: Human-readable packet name
        has_delta: True if this packet supports delta encoding
        fields: List of field specifications in order
    """
    packet_type: int
    name: str
    has_delta: bool
    fields: List[FieldSpec]

    @property
    def key_fields(self) -> List[FieldSpec]:
        """Return only the key fields (always transmitted)."""
        return [f for f in self.fields if f.is_key]

    @property
    def non_key_fields(self) -> List[FieldSpec]:
        """Return only the non-key fields (delta encoded)."""
        return [f for f in self.fields if not f.is_key]

    @property
    def num_bitvector_bits(self) -> int:
        """Number of bits needed in the bitvector."""
        return len(self.non_key_fields)

    @property
    def num_bitvector_bytes(self) -> int:
        """Number of bytes needed to store the bitvector."""
        return (self.num_bitvector_bits + 7) // 8  # Ceiling division


# Packet specifications registry
# Maps packet_type -> PacketSpec
PACKET_SPECS: Dict[int, PacketSpec] = {}


# ============================================================================
# PACKET DEFINITIONS
# ============================================================================
# These definitions are based on freeciv/common/networking/packets.def
# and should be kept in sync with the server's protocol version.

# PACKET_CHAT_MSG = 25
# From packets.def:
#   PACKET_CHAT_MSG = 25; sc, lsend
#     STRING message[MAX_LEN_MSG];
#     TILE tile;           # SINT32
#     EVENT event;         # SINT16
#     TURN turn;           # SINT16
#     PHASE phase;         # SINT16
#     CONNECTION conn_id;  # SINT16

# PACKET_SERVER_INFO = 29
# From packets.def lines 702-705:
#   PACKET_SERVER_INFO = 29; sc, dsend, handle-via-fields
#     STRING version_label[48];
#     UINT32 major_version, minor_version, patch_version, emerg_version;
#   end
PACKET_SPECS[29] = PacketSpec(
    packet_type=29,
    name="PACKET_SERVER_INFO",
    has_delta=True,
    fields=[
        FieldSpec(name='version_label', type_name='STRING'),
        FieldSpec(name='major_version', type_name='UINT32'),
        FieldSpec(name='minor_version', type_name='UINT32'),
        FieldSpec(name='patch_version', type_name='UINT32'),
        FieldSpec(name='emerg_version', type_name='UINT32'),
    ]
)

PACKET_SPECS[25] = PacketSpec(
    packet_type=25,
    name="PACKET_CHAT_MSG",
    has_delta=True,
    fields=[
        FieldSpec(name='message', type_name='STRING'),
        FieldSpec(name='tile', type_name='SINT32'),
        FieldSpec(name='event', type_name='SINT16'),
        FieldSpec(name='turn', type_name='SINT16'),
        FieldSpec(name='phase', type_name='SINT16'),
        FieldSpec(name='conn_id', type_name='SINT16'),
    ]
)


# PACKET_RULESET_CONTROL = 155
# From packets.def lines 1970-2006
PACKET_SPECS[155] = PacketSpec(
    packet_type=155,
    name="PACKET_RULESET_CONTROL",
    has_delta=True,
    fields=[
        # Entity counts (22 UINT16 fields - lines 1971-1994)
        FieldSpec(name='num_unit_classes', type_name='UINT16'),
        FieldSpec(name='num_unit_types', type_name='UINT16'),
        FieldSpec(name='num_impr_types', type_name='UINT16'),
        FieldSpec(name='num_tech_classes', type_name='UINT16'),
        FieldSpec(name='num_tech_types', type_name='UINT16'),
        FieldSpec(name='num_extra_types', type_name='UINT16'),
        FieldSpec(name='num_base_types', type_name='UINT16'),
        FieldSpec(name='num_road_types', type_name='UINT16'),
        FieldSpec(name='num_resource_types', type_name='UINT16'),
        FieldSpec(name='num_goods_types', type_name='UINT16'),
        FieldSpec(name='num_disaster_types', type_name='UINT16'),
        FieldSpec(name='num_achievement_types', type_name='UINT16'),
        FieldSpec(name='num_multipliers', type_name='UINT16'),
        FieldSpec(name='num_styles', type_name='UINT16'),
        FieldSpec(name='num_music_styles', type_name='UINT16'),
        FieldSpec(name='government_count', type_name='UINT16'),
        FieldSpec(name='nation_count', type_name='UINT16'),
        FieldSpec(name='num_city_styles', type_name='UINT16'),
        FieldSpec(name='terrain_count', type_name='UINT16'),
        FieldSpec(name='num_specialist_types', type_name='UINT16'),
        FieldSpec(name='num_nation_groups', type_name='UINT16'),
        FieldSpec(name='num_nation_sets', type_name='UINT16'),
        # Client preferences (lines 1996-1999)
        FieldSpec(name='preferred_tileset', type_name='STRING'),
        FieldSpec(name='preferred_soundset', type_name='STRING'),
        FieldSpec(name='preferred_musicset', type_name='STRING'),
        FieldSpec(name='popup_tech_help', type_name='BOOL'),
        # Ruleset metadata (lines 2001-2005)
        FieldSpec(name='name', type_name='STRING'),
        FieldSpec(name='version', type_name='STRING'),
        FieldSpec(name='alt_dir', type_name='STRING'),
        FieldSpec(name='desc_length', type_name='UINT32'),
        FieldSpec(name='num_counters', type_name='UINT16'),
    ]
)

# PACKET_RULESET_DESCRIPTION_PART = 247
# From packets.def lines 2012-2014:
#   PACKET_RULESET_DESCRIPTION_PART = 247; sc, lsend
#     STRING text[MAX_LEN_CONTENT];
#   end
#
# Multi-part packet: Sent after RULESET_CONTROL in chunks.
# Client accumulates parts until total bytes >= desc_length from RULESET_CONTROL.
PACKET_SPECS[247] = PacketSpec(
    packet_type=247,
    name="PACKET_RULESET_DESCRIPTION_PART",
    has_delta=False,  # Simple packet, no delta encoding
    fields=[
        FieldSpec(name='text', type_name='STRING'),
    ]
)


# PACKET_GAME_INFO = 16
# From packets.def: PACKET_GAME_INFO = 16; sc, is-info
# This packet contains comprehensive game state information including:
# - Array-diff fields: global_advances[A_LAST], great_wonder_owners[B_LAST]
# - Many game configuration parameters
# Note: This is a minimal specification focusing on array-diff fields.
# Full specification has 100+ fields (see packets.def for complete list).
#
# Constants from freeciv/common/fc_types.h:
# - A_LAST = MAX_NUM_ADVANCES + 1 = 401 (technologies)
# - B_LAST = MAX_NUM_BUILDINGS = 200 (buildings/wonders)
PACKET_SPECS[16] = PacketSpec(
    packet_type=16,
    name="PACKET_GAME_INFO",
    has_delta=True,
    fields=[
        # Key field for delta protocol (minimal set - actual packet has no key fields)
        # Non-key fields (partial list - focusing on array-diff fields)
        FieldSpec(name='global_advance_count', type_name='UINT16'),
        # Array-diff field: Boolean array of discovered technologies
        FieldSpec(
            name='global_advances',
            type_name='BOOL',  # Not used for array-diff, element_type is used instead
            is_array=True,
            array_diff=True,
            element_type='BOOL',
            array_size=401,  # A_LAST = MAX_NUM_ADVANCES + 1
            default_value=[]
        ),
        # Array-diff field: Player IDs owning each wonder
        FieldSpec(
            name='great_wonder_owners',
            type_name='SINT8',  # Not used for array-diff, element_type is used instead
            is_array=True,
            array_diff=True,
            element_type='SINT8',  # PLAYER type maps to SINT8
            array_size=200,  # B_LAST = MAX_NUM_BUILDINGS
            default_value=[]
        ),
        # Additional fields would go here...
        # (100+ more fields in actual packet - omitted for minimal implementation)
    ]
)


PACKET_SPECS[143] = PacketSpec(
    packet_type=143,
    name="PACKET_RULESET_GOVERNMENT_RULER_TITLE",
    has_delta=True,
    fields=[
        FieldSpec(name='gov', type_name='SINT8', is_key=False),
        FieldSpec(name='nation', type_name='SINT16', is_key=False),
        FieldSpec(name='male_title', type_name='STRING', is_key=False),
        FieldSpec(name='female_title', type_name='STRING', is_key=False),
    ]
)


PACKET_SPECS[152] = PacketSpec(
    packet_type=152,
    name="PACKET_RULESET_UNIT_CLASS",
    has_delta=True,
    fields=[
        FieldSpec(name='id', type_name='UINT8', is_key=False),
        FieldSpec(name='name', type_name='STRING', is_key=False),
        FieldSpec(name='rule_name', type_name='STRING', is_key=False),
        FieldSpec(name='min_speed', type_name='UINT32', is_key=False),
        FieldSpec(name='hp_loss_pct', type_name='UINT8', is_key=False),
        FieldSpec(name='non_native_def_pct', type_name='UINT16', is_key=False),
        FieldSpec(name='flags', type_name='UINT32', is_key=False),  # 32-bit bitvector
        FieldSpec(name='helptext', type_name='STRING', is_key=False),
    ]
)

PACKET_SPECS[153] = PacketSpec(
    packet_type=153,
    name="PACKET_RULESET_BASE",
    has_delta=True,
    fields=[
        FieldSpec(name='id', type_name='UINT8', is_key=False),
        FieldSpec(name='gui_type', type_name='UINT8', is_key=False),
        FieldSpec(name='border_sq', type_name='SINT8', is_key=False),
        FieldSpec(name='vision_main_sq', type_name='SINT8', is_key=False),
        FieldSpec(name='vision_invis_sq', type_name='SINT8', is_key=False),
        FieldSpec(name='vision_subs_sq', type_name='SINT8', is_key=False),
    ]
)

PACKET_SPECS[229] = PacketSpec(
    packet_type=229,
    name="PACKET_RULESET_UNIT_FLAG",
    has_delta=True,
    fields=[
        FieldSpec(name='id', type_name='UINT8', is_key=False),
        FieldSpec(name='name', type_name='STRING', is_key=False),
        FieldSpec(name='helptxt', type_name='STRING', is_key=False),
    ]
)

PACKET_SPECS[228] = PacketSpec(
    packet_type=228,
    name="PACKET_RULESET_UNIT_BONUS",
    has_delta=True,
    fields=[
        FieldSpec(name='unit', type_name='UINT16', is_key=True),
        FieldSpec(name='flag', type_name='UINT8', is_key=True),
        FieldSpec(name='type', type_name='UINT8', is_key=True),
        FieldSpec(name='value', type_name='SINT16', is_key=True),
        FieldSpec(name='quiet', type_name='BOOL', is_key=True),
    ]
)


# Add more packet specifications as needed following this pattern:
# PACKET_SPECS[<packet_num>] = PacketSpec(
#     packet_type=<packet_num>,
#     name="PACKET_<NAME>",
#     has_delta=True/False,
#     fields=[
#         FieldSpec(name='<field>', type_name='<TYPE>', is_key=True/False),
#         ...
#     ]
# )


def get_packet_spec(packet_type: int) -> PacketSpec:
    """Get packet specification by type number.

    Args:
        packet_type: The numeric packet type

    Returns:
        PacketSpec for the given type

    Raises:
        KeyError: If packet type is not defined
    """
    if packet_type not in PACKET_SPECS:
        raise KeyError(
            f"No specification found for packet type {packet_type}. "
            f"Available types: {sorted(PACKET_SPECS.keys())}"
        )
    return PACKET_SPECS[packet_type]
