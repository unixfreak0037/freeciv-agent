import asyncio
import struct
from typing import Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .delta_cache import DeltaCache

from .packet_specs import PACKET_SPECS, PacketSpec

# Packet type constants
PACKET_PROCESSING_STARTED = 0
PACKET_PROCESSING_FINISHED = 1
PACKET_SERVER_JOIN_REQ = 4
PACKET_SERVER_JOIN_REPLY = 5
PACKET_CHAT_MSG = 25
PACKET_SERVER_INFO = 29
PACKET_RULESET_CONTROL = 155
PACKET_GAME_LOAD = 155
PACKET_RULESET_DESCRIPTION_PART = 247
PACKET_RULESET_SUMMARY = 251
PACKET_RULESET_NATION_SETS = 236

# Version constants
MAJOR_VERSION = 3
MINOR_VERSION = 3
PATCH_VERSION = 90
VERSION_LABEL = "-dev"
CAPABILITY = "+Freeciv.Devel-3.4-2025.Nov.29"


async def _recv_exact(reader: asyncio.StreamReader, num_bytes: int) -> bytes:
    """Read exactly num_bytes from stream, handling partial reads."""
    try:
        data = await reader.readexactly(num_bytes)
        return data
    except asyncio.IncompleteReadError:
        raise ConnectionError("Socket closed while reading data")


# Data type encoding functions

def encode_string(value: str) -> bytes:
    """Encode a STRING as null-terminated UTF-8 bytes."""
    return value.encode('utf-8') + b'\x00'


def encode_bool(value: bool) -> bytes:
    """Encode a BOOL as a single byte (0 or 1)."""
    return struct.pack('B', 1 if value else 0)


def encode_uint32(value: int) -> bytes:
    """Encode a UINT32 as 4 bytes in big-endian format."""
    return struct.pack('>I', value)


# Data type decoding functions

def decode_string(data: bytes, offset: int) -> Tuple[str, int]:
    """
    Decode a null-terminated STRING from bytes.

    Returns:
        Tuple of (string_value, new_offset)
    """
    end = data.find(b'\x00', offset)
    if end == -1:
        raise ValueError("Null terminator not found in string")
    string = data[offset:end].decode('utf-8')
    return string, end + 1


def decode_fixed_string(data: bytes, offset: int, size: int) -> Tuple[str, int]:
    """
    Decode a fixed-size STRING from bytes.

    Fixed-size strings are padded to a specific length and null-terminated
    within that space. We read the fixed number of bytes and decode up to
    the first null terminator.

    Args:
        data: Byte array to read from
        offset: Starting position
        size: Fixed size of the string field in bytes

    Returns:
        Tuple of (string_value, new_offset)
    """
    chunk = data[offset:offset + size]
    # Find null terminator within the fixed-size chunk
    end = chunk.find(b'\x00')
    if end == -1:
        # No null terminator, use entire chunk
        string = chunk.decode('utf-8')
    else:
        # Decode up to null terminator
        string = chunk[:end].decode('utf-8')
    return string, offset + size


def decode_bool(data: bytes, offset: int) -> Tuple[bool, int]:
    """
    Decode a BOOL from bytes.

    Returns:
        Tuple of (bool_value, new_offset)
    """
    value = data[offset] != 0
    return value, offset + 1


def decode_uint32(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode a UINT32 from bytes (big-endian).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack('>I', data[offset:offset+4])[0]
    return value, offset + 4


def decode_sint16(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode SINT16 (big-endian signed 16-bit).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack('>h', data[offset:offset+2])[0]
    return value, offset + 2


def decode_uint16(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode UINT16 (big-endian unsigned 16-bit).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack('>H', data[offset:offset+2])[0]
    return value, offset + 2


def decode_sint32(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode SINT32 (big-endian signed 32-bit).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack('>i', data[offset:offset+4])[0]
    return value, offset + 4


def encode_packet(packet_type: int, payload: bytes) -> bytes:
    """
    Encode a packet with a header.
    """
    packet_length = len(payload) + 3  # 2 bytes length + 1 byte type + payload
    length_header = struct.pack('>H', packet_length)
    return length_header + struct.pack('B', packet_type) + payload


def encode_server_join_req(username: str) -> bytes:
    """
    Encode a PACKET_SERVER_JOIN_REQ packet.

    Packet structure:
    - STRING username[48]
    - STRING capability[512]
    - STRING version_label[48]
    - UINT32 major_version
    - UINT32 minor_version
    - UINT32 patch_version
    """
    # Build packet payload (without header)
    payload = (encode_string(username) +
               encode_string(CAPABILITY) +
               encode_string(VERSION_LABEL) +
               encode_uint32(MAJOR_VERSION) +
               encode_uint32(MINOR_VERSION) +
               encode_uint32(PATCH_VERSION))

    # Build complete packet with header
    return encode_packet(PACKET_SERVER_JOIN_REQ, payload)


async def read_packet(reader: asyncio.StreamReader, use_two_byte_type: bool = False) -> Tuple[int, bytes, bytes]:
    """
    Read a packet from the stream.

    Args:
        reader: The stream reader
        use_two_byte_type: If True, read 2 bytes for packet type (after JOIN_REPLY accepted)

    Returns:
        Tuple of (packet_type, payload_data, raw_packet_bytes)
        where raw_packet_bytes includes the complete packet with header
    """
    # Read 2-byte length field (big-endian)
    length_bytes = await _recv_exact(reader, 2)
    packet_length = struct.unpack('>H', length_bytes)[0]

    # Read packet type (1 or 2 bytes depending on connection state)
    if use_two_byte_type:
        type_bytes = await _recv_exact(reader, 2)
        packet_type = struct.unpack('>H', type_bytes)[0]
        header_size = 4  # 2 bytes length + 2 bytes type
    else:
        type_bytes = await _recv_exact(reader, 1)
        packet_type = struct.unpack('B', type_bytes)[0]
        header_size = 3  # 2 bytes length + 1 byte type

    # Read remaining payload
    payload_length = packet_length - header_size
    payload = await _recv_exact(reader, payload_length) if payload_length > 0 else b''

    # Construct complete raw packet for debugging
    raw_packet = length_bytes + type_bytes + payload

    return packet_type, payload, raw_packet


def decode_server_join_reply(payload: bytes) -> dict:
    """
    Decode a PACKET_SERVER_JOIN_REPLY packet.

    Packet structure:
    - BOOL you_can_join
    - STRING message[1536]
    - STRING capability[512]
    - STRING challenge_file[4095]
    """
    offset = 0

    # Parse BOOL you_can_join
    you_can_join, offset = decode_bool(payload, offset)

    # Parse STRING fields
    message, offset = decode_string(payload, offset)
    capability, offset = decode_string(payload, offset)
    challenge_file, offset = decode_string(payload, offset)

    return {
        'you_can_join': you_can_join,
        'message': message,
        'capability': capability,
        'challenge_file': challenge_file
    }


def decode_server_info(payload: bytes) -> dict:
    """
    Decode PACKET_SERVER_INFO packet.

    Packet structure (from packets.def line 705):
    - STRING version_label[48]
    - UINT32 major_version
    - UINT32 minor_version
    - UINT32 patch_version
    - UINT32 emerg_version
    """
    offset = 0

    version_label, offset = decode_string(payload, offset)
    major_version, offset = decode_uint32(payload, offset)
    minor_version, offset = decode_uint32(payload, offset)
    patch_version, offset = decode_uint32(payload, offset)
    emerg_version, offset = decode_uint32(payload, offset)

    return {
        'version_label': version_label,
        'major_version': major_version,
        'minor_version': minor_version,
        'patch_version': patch_version,
        'emerg_version': emerg_version
    }


def decode_chat_msg(payload: bytes) -> dict:
    """
    DEPRECATED: Use decode_delta_packet() for proper delta protocol support.

    Legacy decoder for PACKET_CHAT_MSG that uses length-based guessing
    to handle omitted fields. This approach is unreliable and doesn't
    properly implement the delta protocol.

    Use decode_delta_packet() with PACKET_SPECS[PACKET_CHAT_MSG] instead.

    Packet structure (from packets.def line 676):
    - STRING message[MAX_LEN_MSG]  # 1537 bytes max
    - TILE tile                     # SINT32 (4 bytes)
    - EVENT event                   # sint16 (2 bytes)
    - TURN turn                     # SINT16 (2 bytes)
    - PHASE phase                   # SINT16 (2 bytes) - may be omitted via delta encoding
    - CONNECTION conn_id            # SINT16 (2 bytes) - may be omitted via delta encoding

    Note: FreeCiv uses delta encoding for this packet, so phase and conn_id
    may be omitted if unchanged from previous values.

    Returns dictionary with keys:
      message, tile, event, turn, phase, conn_id
    """
    offset = 0

    message, offset = decode_string(payload, offset)
    tile, offset = decode_sint32(payload, offset)
    event, offset = decode_sint16(payload, offset)
    turn, offset = decode_sint16(payload, offset)

    # Phase and conn_id may be omitted via delta encoding
    if len(payload) - offset >= 4:
        phase, offset = decode_sint16(payload, offset)
        conn_id, offset = decode_sint16(payload, offset)
    else:
        # Use defaults when fields are omitted
        phase = 0
        conn_id = -1

    return {
        'message': message,
        'tile': tile,
        'event': event,
        'turn': turn,
        'phase': phase,
        'conn_id': conn_id
    }


def decode_ruleset_summary(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_SUMMARY packet.

    Packet structure (from packets.def line 2013):
    - STRING text[MAX_LEN_CONTENT]  # 4076 bytes max

    Returns dictionary with key: text
    """
    offset = 0
    text, offset = decode_string(payload, offset)

    return {
        'text': text
    }


def decode_ruleset_description_part(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_DESCRIPTION_PART packet.

    Packet structure (from packets.def lines 2012-2014):
    - STRING text[MAX_LEN_CONTENT]  # 4076 bytes max

    This packet is sent in multiple parts after PACKET_RULESET_CONTROL.
    The client must accumulate all parts until the total size matches
    or exceeds the desc_length field from RULESET_CONTROL.

    Returns dictionary with key: text
    """
    offset = 0
    text, offset = decode_string(payload, offset)

    return {
        'text': text
    }


def decode_ruleset_nation_sets(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_NATION_SETS packet with delta protocol support.

    This packet uses delta protocol encoding, which means it starts with a bitvector
    indicating which fields are present in the packet.

    Packet structure (from packets.def lines 1603-1610):
    - BITVECTOR (1 byte) - indicates which fields are present
      Bit 0: nsets field present
      Bit 1: names array present
      Bit 2: rule_names array present
      Bit 3: descriptions array present
    - UINT8 nsets (count of nation sets, 0-32) - if bit 0 is set
    - STRING names[nsets] (null-terminated variable-length strings) - if bit 1 is set
    - STRING rule_names[nsets] (null-terminated variable-length strings) - if bit 2 is set
    - STRING descriptions[nsets] (null-terminated variable-length strings) - if bit 3 is set

    Note: Despite the MAX_LEN_NAME and MAX_LEN_MSG constants in packets.def, FreeCiv
    transmits strings as null-terminated variable-length, NOT fixed-size.

    Returns dictionary with keys:
      nsets (int), names (list), rule_names (list), descriptions (list)
    """
    offset = 0

    # Read delta protocol bitvector (1 byte for 4 fields)
    bitvector = payload[offset]
    offset += 1

    # Check which fields are present
    has_nsets = bool(bitvector & (1 << 0))
    has_names = bool(bitvector & (1 << 1))
    has_rule_names = bool(bitvector & (1 << 2))
    has_descriptions = bool(bitvector & (1 << 3))

    # Read nsets if present (should always be present in first packet)
    if has_nsets:
        nsets = payload[offset]
        offset += 1
    else:
        # In delta protocol, missing fields would come from cache
        # For first packet, nsets should always be present
        nsets = 0

    # Read names array (null-terminated strings)
    names = []
    if has_names:
        for i in range(nsets):
            name, offset = decode_string(payload, offset)
            names.append(name)

    # Read rule_names array (null-terminated strings)
    rule_names = []
    if has_rule_names:
        for i in range(nsets):
            rule_name, offset = decode_string(payload, offset)
            rule_names.append(rule_name)

    # Read descriptions array (null-terminated strings)
    descriptions = []
    if has_descriptions:
        for i in range(nsets):
            description, offset = decode_string(payload, offset)
            descriptions.append(description)

    return {
        'nsets': nsets,
        'names': names,
        'rule_names': rule_names,
        'descriptions': descriptions
    }


# ============================================================================
# Delta Protocol Support
# ============================================================================

def read_bitvector(data: bytes, offset: int, num_bits: int) -> Tuple[int, int]:
    """
    Read a bitvector from payload.

    The bitvector is used in delta encoding to indicate which fields are present
    in the packet. Each bit corresponds to a non-key field (bit 0 = first field,
    bit 1 = second field, etc.). A bit value of 1 means the field is included
    in the payload.

    FreeCiv bitvectors are stored as byte arrays where each byte contains 8 bits
    with LSB-first ordering within each byte. This means byte 0 contains bits 0-7,
    byte 1 contains bits 8-15, etc. To properly decode this in Python, we must
    use little-endian byte order when converting to an integer.

    Args:
        data: Payload bytes
        offset: Starting offset in the payload
        num_bits: Number of bits in bitvector (equal to number of non-key fields)

    Returns:
        Tuple of (bitvector_as_int, new_offset)
        bitvector_as_int is an integer where bit positions can be tested with (value & (1 << bit_index))
    """
    num_bytes = (num_bits + 7) // 8  # Ceiling division
    bitvector_bytes = data[offset:offset + num_bytes]
    # Use 'little' because FreeCiv stores bitvectors as byte arrays with LSB-first in each byte
    bitvector = int.from_bytes(bitvector_bytes, 'little')
    return bitvector, offset + num_bytes


def is_bit_set(bitvector: int, bit_index: int) -> bool:
    """Check if a specific bit is set in bitvector.

    Args:
        bitvector: Integer representation of the bitvector
        bit_index: Zero-based index of the bit to check (0 = LSB)

    Returns:
        True if the bit is set (1), False otherwise (0)
    """
    return (bitvector & (1 << bit_index)) != 0


def _decode_field(data: bytes, offset: int, type_name: str) -> Tuple[Any, int]:
    """Decode a single field based on its type.

    Args:
        data: Payload bytes
        offset: Current offset in the payload
        type_name: FreeCiv type name ('STRING', 'SINT32', etc.)

    Returns:
        Tuple of (decoded_value, new_offset)

    Raises:
        ValueError: If type_name is not supported
    """
    if type_name == 'STRING':
        return decode_string(data, offset)
    elif type_name == 'SINT32':
        return decode_sint32(data, offset)
    elif type_name == 'SINT16':
        return decode_sint16(data, offset)
    elif type_name == 'UINT16':
        return decode_uint16(data, offset)
    elif type_name == 'UINT32':
        return decode_uint32(data, offset)
    elif type_name == 'BOOL':
        return decode_bool(data, offset)
    else:
        raise ValueError(f"Unsupported field type: {type_name}")


def decode_delta_packet(
    payload: bytes,
    packet_spec: PacketSpec,
    delta_cache: 'DeltaCache'
) -> dict:
    """
    Generic delta decoder for any packet with delta support.

    This decoder implements FreeCiv's delta protocol:
    1. Read key fields (always present, not in bitvector)
    2. Read bitvector indicating which non-key fields are present
    3. For each non-key field:
       - If bit is set: read new value from payload
       - If bit is clear: use cached value from previous packet
    4. Update cache with complete packet

    Args:
        payload: Raw packet payload (after header)
        packet_spec: Packet specification from PACKET_SPECS
        delta_cache: Delta cache instance for this connection

    Returns:
        Complete field dictionary with all values (from payload or cache)
    """
    offset = 0
    fields = {}

    # Step 1: Read key fields (always present, always transmitted)
    key_values = []
    for field_spec in packet_spec.key_fields:
        value, offset = _decode_field(payload, offset, field_spec.type_name)
        fields[field_spec.name] = value
        key_values.append(value)

    key_tuple = tuple(key_values)

    # Step 2: Read bitvector (if packet has non-key fields)
    if packet_spec.num_bitvector_bits > 0:
        bitvector, offset = read_bitvector(
            payload, offset, packet_spec.num_bitvector_bits
        )
    else:
        bitvector = 0

    # Step 3: Get cached packet (or use defaults if no cache exists)
    cached = delta_cache.get_cached_packet(packet_spec.packet_type, key_tuple)
    if cached is None:
        # No cached packet - use default values for all non-key fields
        cached = {
            field.name: field.default_value
            for field in packet_spec.non_key_fields
        }

    # Step 4: Read non-key fields based on bitvector
    for bit_index, field_spec in enumerate(packet_spec.non_key_fields):
        if field_spec.is_bool:
            # Boolean header-folding optimization: the bit value IS the field value
            # No separate byte is transmitted for boolean fields
            fields[field_spec.name] = is_bit_set(bitvector, bit_index)
        elif is_bit_set(bitvector, bit_index):
            # Field changed - read new value from payload
            value, offset = _decode_field(payload, offset, field_spec.type_name)
            fields[field_spec.name] = value
        else:
            # Field unchanged - use cached value
            fields[field_spec.name] = cached[field_spec.name]

    # Step 5: Update cache with complete packet
    delta_cache.update_cache(packet_spec.packet_type, key_tuple, fields)

    return fields
