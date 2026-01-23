import asyncio
import struct
import zlib
from typing import Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .delta_cache import DeltaCache

from .packet_specs import PACKET_SPECS, PacketSpec

# Packet type constants
PACKET_PROCESSING_STARTED = 0
PACKET_PROCESSING_FINISHED = 1
PACKET_SERVER_JOIN_REQ = 4
PACKET_SERVER_JOIN_REPLY = 5
PACKET_GAME_INFO = 16
PACKET_CHAT_MSG = 25
PACKET_SERVER_INFO = 29
PACKET_RULESET_CONTROL = 155
PACKET_GAME_LOAD = 155
PACKET_RULESET_NATION_GROUPS = 147
PACKET_RULESET_NATION = 148
PACKET_RULESET_DESCRIPTION_PART = 247
PACKET_RULESET_SUMMARY = 251
PACKET_RULESET_NATION_SETS = 236
PACKET_NATION_AVAILABILITY = 237
PACKET_RULESET_GAME = 141
PACKET_RULESET_DISASTER = 224

# Version constants
MAJOR_VERSION = 3
MINOR_VERSION = 2
PATCH_VERSION = 2
VERSION_LABEL = ""
CAPABILITY = "+Freeciv-3.2-network ownernull16 unignoresync tu32 hap2clnt"

# Compression constants (from freeciv/common/networking/packets.c:53,58,63)
COMPRESSION_BORDER = 16385  # 16*1024 + 1 - packets >= this size are compressed
JUMBO_SIZE = 65535          # 0xffff - marker for jumbo packets
JUMBO_BORDER = 49150        # 64*1024 - COMPRESSION_BORDER - 1

# Compression-related packet types
PACKET_FREEZE_CLIENT = 130  # Start compression grouping
PACKET_THAW_CLIENT = 131    # End compression grouping


async def _recv_exact(reader: asyncio.StreamReader, num_bytes: int) -> bytes:
    """Read exactly num_bytes from stream, handling partial reads."""
    try:
        data = await reader.readexactly(num_bytes)
        return data
    except asyncio.IncompleteReadError:
        raise ConnectionError("Socket closed while reading data")


def _decompress_packet(compressed_data: bytes) -> bytes:
    """
    Decompress a zlib-compressed packet buffer.

    Compressed packets contain multiple concatenated packets in DEFLATE format.

    Args:
        compressed_data: Raw compressed bytes (DEFLATE format)

    Returns:
        Decompressed buffer containing concatenated packets

    Raises:
        ValueError: If decompression fails (corrupt data, invalid format)
    """
    try:
        decompressed = zlib.decompress(compressed_data)
        return decompressed
    except zlib.error as e:
        raise ValueError(f"Decompression failed: {e}") from e


async def _parse_packet_buffer(
    buffer: bytes,
    use_two_byte_type: bool
) -> list:
    """
    Parse multiple packets from a decompressed buffer.

    Decompressed buffers contain concatenated packets, each with normal
    header (length + type).

    Args:
        buffer: Decompressed buffer containing multiple packets
        use_two_byte_type: Whether to use 2-byte type field (after JOIN_REPLY)

    Returns:
        List of (packet_type, payload, raw_packet_bytes) tuples

    Raises:
        ValueError: If buffer contains invalid packet structure
    """
    packets = []
    offset = 0

    while offset < len(buffer):
        # Need at least 3 bytes for minimum header
        if len(buffer) - offset < 3:
            raise ValueError(
                f"Incomplete packet header at offset {offset}: "
                f"only {len(buffer) - offset} bytes remaining"
            )

        # Read length (big-endian)
        packet_length = struct.unpack('>H', buffer[offset:offset+2])[0]

        # Read type field (1 or 2 bytes)
        if use_two_byte_type:
            header_size = 4
            if len(buffer) - offset < header_size:
                raise ValueError(
                    f"Incomplete 2-byte type header at offset {offset}"
                )
            packet_type = struct.unpack('>H', buffer[offset+2:offset+4])[0]
        else:
            header_size = 3
            packet_type = struct.unpack('B', buffer[offset+2:offset+3])[0]

        # Validate length
        if packet_length < header_size:
            raise ValueError(
                f"Invalid packet length {packet_length} at offset {offset}"
            )

        # Check if complete packet available
        if offset + packet_length > len(buffer):
            raise ValueError(
                f"Incomplete packet at offset {offset}: "
                f"need {packet_length} bytes, have {len(buffer) - offset}"
            )

        # Extract payload and raw packet
        payload_start = offset + header_size
        payload_length = packet_length - header_size
        payload = buffer[payload_start:payload_start + payload_length]
        raw_packet = buffer[offset:offset + packet_length]

        packets.append((packet_type, payload, raw_packet))
        offset += packet_length

    return packets


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


def encode_sint16(value: int) -> bytes:
    """Encode a SINT16 as 2 bytes in big-endian format."""
    return struct.pack('>h', value)


def encode_uint8(value: int) -> bytes:
    """Encode a UINT8 as 1 byte."""
    return struct.pack('B', value)


def encode_sint8(value: int) -> bytes:
    """Encode a SINT8 as 1 byte (signed)."""
    return struct.pack('b', value)


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


def decode_uint8(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode UINT8 (unsigned 8-bit integer).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = data[offset]
    return value, offset + 1


def decode_sint8(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode SINT8 (signed 8-bit integer).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack('b', bytes([data[offset]]))[0]
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


async def read_packet(reader: asyncio.StreamReader, use_two_byte_type: bool = False, validate: bool = False) -> Tuple[int, bytes, bytes]:
    """
    Read a packet from the stream.

    Args:
        reader: The stream reader
        use_two_byte_type: If True, read 2 bytes for packet type (after JOIN_REPLY accepted)
        validate: If True, enable validation logging and assertions for debugging

    Returns:
        Tuple of (packet_type, payload_data, raw_packet_bytes)
        where raw_packet_bytes includes the complete packet with header
    """
    # Read 2-byte length field (big-endian)
    length_bytes = await _recv_exact(reader, 2)
    packet_length = struct.unpack('>H', length_bytes)[0]

    if validate:
        print(f"[VALIDATE] Length header: {packet_length} bytes")

    # ============================================================================
    # COMPRESSION DETECTION AND HANDLING
    # ============================================================================

    # Check for JUMBO compressed packet
    if packet_length == JUMBO_SIZE:
        # Read 4-byte actual length (big-endian)
        jumbo_length_bytes = await _recv_exact(reader, 4)
        actual_length = struct.unpack('>I', jumbo_length_bytes)[0]

        if validate:
            print(f"[VALIDATE] JUMBO compressed: {actual_length} bytes")

        # Read compressed data (subtract 6-byte header)
        compressed_size = actual_length - 6
        compressed_data = await _recv_exact(reader, compressed_size)

        # Decompress and parse
        try:
            decompressed = _decompress_packet(compressed_data)
            packets = await _parse_packet_buffer(decompressed, use_two_byte_type)
        except ValueError as e:
            raise ConnectionError(f"JUMBO decompression failed: {e}") from e

        if not packets:
            raise ValueError("JUMBO packet contained no packets")

        # Return first packet (raise if multiple)
        if len(packets) > 1:
            raise NotImplementedError(
                f"JUMBO packet contains {len(packets)} packets, "
                f"multi-packet buffering not implemented"
            )

        return packets[0]

    # Check for normal compressed packet
    elif packet_length >= COMPRESSION_BORDER:
        compressed_size = packet_length - COMPRESSION_BORDER

        if validate:
            print(f"[VALIDATE] Compressed: {compressed_size} bytes")

        # Read compressed data
        compressed_data = await _recv_exact(reader, compressed_size)

        # Decompress and parse
        try:
            decompressed = _decompress_packet(compressed_data)
            packets = await _parse_packet_buffer(decompressed, use_two_byte_type)
        except ValueError as e:
            raise ConnectionError(f"Decompression failed: {e}") from e

        if not packets:
            raise ValueError("Compressed packet contained no packets")

        # Return first packet (raise if multiple)
        if len(packets) > 1:
            raise NotImplementedError(
                f"Compressed packet contains {len(packets)} packets, "
                f"multi-packet buffering not implemented"
            )

        return packets[0]

    # ============================================================================
    # UNCOMPRESSED PACKET (EXISTING CODE - NO CHANGES BELOW THIS LINE)
    # ============================================================================

    # Read packet type (1 or 2 bytes depending on connection state)
    if use_two_byte_type:
        type_bytes = await _recv_exact(reader, 2)
        packet_type = struct.unpack('>H', type_bytes)[0]
        header_size = 4  # 2 bytes length + 2 bytes type
    else:
        type_bytes = await _recv_exact(reader, 1)
        packet_type = struct.unpack('B', type_bytes)[0]
        header_size = 3  # 2 bytes length + 1 byte type

    if validate:
        print(f"[VALIDATE] Type field: {len(type_bytes)} bytes (packet type {packet_type})")

    # Read remaining payload
    payload_length = packet_length - header_size
    payload = await _recv_exact(reader, payload_length) if payload_length > 0 else b''

    if validate:
        print(f"[VALIDATE] Payload length: {payload_length} bytes")

    # Construct complete raw packet for debugging
    raw_packet = length_bytes + type_bytes + payload

    if validate:
        print(f"[VALIDATE] Reconstructed raw_packet: {len(raw_packet)} bytes")

        # Critical assertion: reconstructed size must match header
        if len(raw_packet) != packet_length:
            raise RuntimeError(
                f"Packet reconstruction error for type {packet_type}: "
                f"header claims {packet_length} bytes, "
                f"but reconstructed {len(raw_packet)} bytes"
            )
        print(f"[VALIDATE] ✓ Packet {packet_type} reconstruction verified")

    return packet_type, payload, raw_packet


def decode_server_join_reply(payload: bytes) -> dict:
    """
    Decode a PACKET_SERVER_JOIN_REPLY packet.

    Packet structure:
    - BOOL you_can_join
    - STRING message[1536]
    - STRING capability[512]
    - STRING challenge_file[4095]
    - CONNECTION conn_id (SINT16)
    """
    offset = 0

    # Parse BOOL you_can_join
    you_can_join, offset = decode_bool(payload, offset)

    # Parse STRING fields
    message, offset = decode_string(payload, offset)
    capability, offset = decode_string(payload, offset)
    challenge_file, offset = decode_string(payload, offset)

    # Parse CONNECTION conn_id (SINT16)
    conn_id, offset = decode_sint16(payload, offset)

    return {
        'you_can_join': you_can_join,
        'message': message,
        'capability': capability,
        'challenge_file': challenge_file,
        'conn_id': conn_id
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


def decode_ruleset_nation_groups(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_NATION_GROUPS packet with delta protocol support.

    This packet uses delta protocol encoding, which means it starts with a bitvector
    indicating which fields are present in the packet.

    Packet structure (from packets.def lines 1612-1616):
    - BITVECTOR (1 byte) - indicates which fields are present
      Bit 0: ngroups field present
      Bit 1: groups array present
      Bit 2: hidden array present
    - UINT8 ngroups (count of nation groups, 0-255) - if bit 0 is set
    - STRING groups[ngroups] (null-terminated variable-length strings) - if bit 1 is set
    - BOOL hidden[ngroups] (1 byte each, 0x00=false, non-zero=true) - if bit 2 is set

    Note: Despite the MAX_LEN_NAME constant in packets.def, FreeCiv
    transmits strings as null-terminated variable-length, NOT fixed-size.

    Returns dictionary with keys:
      ngroups (int), groups (list), hidden (list)
    """
    offset = 0

    # Read delta protocol bitvector (1 byte for 3 fields)
    bitvector = payload[offset]
    offset += 1

    # Check which fields are present
    has_ngroups = bool(bitvector & (1 << 0))
    has_groups = bool(bitvector & (1 << 1))
    has_hidden = bool(bitvector & (1 << 2))

    # Read ngroups if present (should always be present in first packet)
    if has_ngroups:
        ngroups = payload[offset]
        offset += 1
    else:
        # In delta protocol, missing fields would come from cache
        # For first packet, ngroups should always be present
        ngroups = 0

    # Read groups array (null-terminated strings)
    groups = []
    if has_groups:
        for i in range(ngroups):
            group, offset = decode_string(payload, offset)
            groups.append(group)

    # Read hidden array (boolean values, 1 byte each)
    hidden = []
    if has_hidden:
        for i in range(ngroups):
            hidden_byte = payload[offset]
            hidden.append(bool(hidden_byte))
            offset += 1

    return {
        'ngroups': ngroups,
        'groups': groups,
        'hidden': hidden
    }


def decode_ruleset_nation(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_NATION packet using delta protocol.

    Based on FreeCiv source code analysis (common/generate_packets.py):
    - Only the 'id' field is a KEY field (always transmitted)
    - ALL other 24 fields are NON-KEY fields (conditional based on bitvector)
    - Bitvector has 24 bits (3 bytes) for the 24 non-key fields
    - When a bit is set, the corresponding field is present in the payload
    - When a bit is clear, use default/cached value (we use defaults since no cache)

    IMPORTANT: Delta Protocol Field Order
    - FreeCiv's delta protocol transmits bitvector BEFORE key fields
    - This is confirmed in common/generate_packets.py lines 2267-2282
    - Key fields are always present but come after the bitvector

    IMPORTANT: Boolean Header Folding Optimization
    - Standalone BOOL fields (like is_playable) use "boolean header folding"
    - The bitvector bit IS the field value (True if set, False if clear)
    - NO payload bytes are consumed for standalone BOOL fields
    - This provides 8x compression for boolean data
    - BOOL arrays (like leader_is_male[]) still transmit each element as a byte

    Packet structure:
    - BITVECTOR (3 bytes, 24 bits) - indicates which non-key fields are present
    - NATION id (SINT16) - key field, always present after bitvector
    - Conditional fields based on bitvector bits

    Returns dictionary with all nation fields.
    """
    offset = 0

    # IMPORTANT: In delta protocol, bitvector comes BEFORE key fields!
    # This matches FreeCiv's generate_packets.py: bitvector first, then key fields

    # Read delta protocol bitvector FIRST (3 bytes = 24 bits for 24 non-key fields)
    bitvector = int.from_bytes(payload[offset:offset+3], byteorder='little')
    offset += 3

    # Read key field (id) SECOND - always present after bitvector
    nation_id, offset = decode_sint16(payload, offset)

    # Initialize result with key field
    result = {'id': nation_id}

    # Helper to check if bit is set
    def has_field(bit_index):
        return bool(bitvector & (1 << bit_index))

    # Initialize all fields with defaults
    result.update({
        'translation_domain': '', 'adjective': '', 'rule_name': '', 'noun_plural': '',
        'graphic_str': '', 'graphic_alt': '', 'legend': '',
        'style': 0, 'leader_count': 0, 'leader_name': [], 'leader_is_male': [],
        'is_playable': False, 'barbarian_type': 0,
        'nsets': 0, 'sets': [], 'ngroups': 0, 'groups': [],
        'init_government_id': -1, 'init_techs_count': 0, 'init_techs': [],
        'init_units_count': 0, 'init_units': [], 'init_buildings_count': 0, 'init_buildings': []
    })

    # Read ONLY the fields indicated by the bitvector

    if has_field(0):  # translation_domain
        result['translation_domain'], offset = decode_string(payload, offset)

    if has_field(1):  # adjective
        result['adjective'], offset = decode_string(payload, offset)

    if has_field(2):  # rule_name
        result['rule_name'], offset = decode_string(payload, offset)

    if has_field(3):  # noun_plural
        result['noun_plural'], offset = decode_string(payload, offset)

    if has_field(4):  # graphic_str
        result['graphic_str'], offset = decode_string(payload, offset)

    if has_field(5):  # graphic_alt
        result['graphic_alt'], offset = decode_string(payload, offset)

    if has_field(6):  # legend
        result['legend'], offset = decode_string(payload, offset)

    if has_field(7):  # style
        result['style'], offset = decode_uint8(payload, offset)

    if has_field(8):  # leader_count
        result['leader_count'], offset = decode_uint8(payload, offset)

    if has_field(9):  # leader_name[]
        result['leader_name'] = []
        for i in range(result['leader_count']):
            name, offset = decode_string(payload, offset)
            result['leader_name'].append(name)

    if has_field(10):  # leader_is_male[] (BOOL array)
        # Note: Arrays of BOOLs transmit each element as a byte in the payload
        # (boolean header folding only applies to standalone BOOL fields)
        result['leader_is_male'] = []
        for i in range(result['leader_count']):
            is_male, offset = decode_bool(payload, offset)
            result['leader_is_male'].append(is_male)

    # Field 11: is_playable (BOOL) - uses boolean header folding
    # The bitvector bit IS the field value; no payload bytes consumed
    if has_field(11):
        result['is_playable'] = True
    else:
        result['is_playable'] = False

    if has_field(12):  # barbarian_type
        result['barbarian_type'], offset = decode_uint8(payload, offset)

    if has_field(13):  # nsets
        result['nsets'], offset = decode_uint8(payload, offset)

    if has_field(14):  # sets[]
        result['sets'] = []
        for i in range(result['nsets']):
            set_id, offset = decode_uint8(payload, offset)
            result['sets'].append(set_id)

    if has_field(15):  # ngroups
        result['ngroups'], offset = decode_uint8(payload, offset)

    if has_field(16):  # groups[]
        result['groups'] = []
        for i in range(result['ngroups']):
            group_id, offset = decode_uint8(payload, offset)
            result['groups'].append(group_id)

    if has_field(17):  # init_government_id
        result['init_government_id'], offset = decode_sint8(payload, offset)

    if has_field(18):  # init_techs_count
        result['init_techs_count'], offset = decode_uint8(payload, offset)

    if has_field(19):  # init_techs[]
        result['init_techs'] = []
        for i in range(result['init_techs_count']):
            tech_id, offset = decode_uint16(payload, offset)
            result['init_techs'].append(tech_id)

    if has_field(20):  # init_units_count
        result['init_units_count'], offset = decode_uint8(payload, offset)

    if has_field(21):  # init_units[]
        result['init_units'] = []
        for i in range(result['init_units_count']):
            unit_id, offset = decode_uint16(payload, offset)
            result['init_units'].append(unit_id)

    if has_field(22):  # init_buildings_count
        result['init_buildings_count'], offset = decode_uint8(payload, offset)

    if has_field(23):  # init_buildings[]
        result['init_buildings'] = []
        for i in range(result['init_buildings_count']):
            building_id, offset = decode_uint8(payload, offset)
            result['init_buildings'].append(building_id)

    return result


def decode_nation_availability(payload: bytes) -> dict:
    """
    Decode PACKET_NATION_AVAILABILITY packet using delta protocol.

    This packet indicates which nations are available for player selection.
    Uses delta encoding with boolean header folding for nationset_change field.

    Packet structure (from packets.def lines 1650-1654):
    - BITVECTOR (1 byte for 3 non-key fields)
    - UINT16 ncount (little-endian) - Field 0
    - BOOL is_pickable[ncount] (1 byte each) - Field 1
    - BOOL nationset_change (folded into bitvector bit 2) - Field 2

    IMPORTANT: This packet has NO key fields, so all fields are conditional
    based on the bitvector. The nationset_change field uses boolean header
    folding, meaning its value is stored directly in bitvector bit 2 and
    consumes NO payload bytes.

    Returns dictionary with keys:
      ncount (int), is_pickable (list[bool]), nationset_change (bool)
    """
    offset = 0

    # Read delta protocol bitvector (1 byte for 3 fields)
    bitvector = payload[offset]
    offset += 1

    # Initialize result with defaults
    result = {
        'ncount': 0,
        'is_pickable': [],
        'nationset_change': False
    }

    # Field 0: ncount (UINT16, big-endian)
    if bitvector & (1 << 0):
        # Note: FreeCiv uses big-endian for multi-byte integers (consistent with rest of protocol)
        ncount = int.from_bytes(payload[offset:offset+2], byteorder='big')
        offset += 2
        result['ncount'] = ncount

    # Field 1: is_pickable (BOOL array)
    if bitvector & (1 << 1):
        ncount = result['ncount']
        is_pickable = []
        for i in range(ncount):
            pickable = bool(payload[offset])
            is_pickable.append(pickable)
            offset += 1
        result['is_pickable'] = is_pickable

    # Field 2: nationset_change (BOOL, folded into bitvector)
    # Boolean header folding: the bitvector bit IS the field value
    # No payload bytes consumed for this field
    result['nationset_change'] = bool(bitvector & (1 << 2))

    return result


def decode_ruleset_game(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_GAME packet (type 141).

    This packet transmits core ruleset game settings including veteran system
    configuration and UI background color.

    WARNING: The actual packet structure does NOT match packets.def lines 1490-1508!
    The observed structure (FreeCiv 3.2.2) is:
    - 4 unknown UINT8 fields (purpose unclear - may be version-specific)
    - UINT8 veteran_levels
    - STRING veteran_name[veteran_levels][MAX_LEN_NAME]
    - UINT16 power_fact[veteran_levels]
    - MOVEFRAGS move_bonus[veteran_levels]                   # MOVEFRAGS = UINT32
    - UINT8 base_raise_chance[veteran_levels]
    - UINT8 work_raise_chance[veteran_levels]
    - UINT8 background_red
    - UINT8 background_green
    - UINT8 background_blue

    The packets.def specification shows default_specialist, global_init_techs, and
    global_init_buildings should come first, but they are not present in the observed
    packet structure. This may be a version-specific difference or conditional compilation.

    TODO: Investigate actual packet generation code to determine correct structure.

    This is a non-delta protocol packet - all fields are always present.

    Returns dictionary with all packet fields.
    """
    offset = 0

    # Skip 4 unknown bytes at the start
    # Observed values: 248, 63, 1, 23 (meaning unclear)
    unknown_bytes = []
    for i in range(4):
        val, offset = decode_uint8(payload, offset)
        unknown_bytes.append(val)

    # Set missing fields to defaults (not present in actual packet)
    default_specialist = 0
    global_init_techs_count = 0
    global_init_techs = []
    global_init_buildings_count = 0
    global_init_buildings = []

    # Veteran system configuration
    veteran_levels, offset = decode_uint8(payload, offset)

    # Veteran names (variable-length strings)
    veteran_name = []
    for i in range(veteran_levels):
        name, offset = decode_string(payload, offset)
        veteran_name.append(name)

    # Veteran power factors (UINT16 each)
    power_fact = []
    for i in range(veteran_levels):
        power, offset = decode_uint16(payload, offset)
        power_fact.append(power)

    # Veteran move bonuses (MOVEFRAGS = UINT32 each)
    move_bonus = []
    for i in range(veteran_levels):
        bonus, offset = decode_uint32(payload, offset)
        move_bonus.append(bonus)

    # Base raise chance (UINT8 each)
    base_raise_chance = []
    for i in range(veteran_levels):
        chance, offset = decode_uint8(payload, offset)
        base_raise_chance.append(chance)

    # Work raise chance (UINT8 each)
    work_raise_chance = []
    for i in range(veteran_levels):
        chance, offset = decode_uint8(payload, offset)
        work_raise_chance.append(chance)

    # Background color (RGB)
    background_red, offset = decode_uint8(payload, offset)
    background_green, offset = decode_uint8(payload, offset)
    background_blue, offset = decode_uint8(payload, offset)

    return {
        'default_specialist': default_specialist,
        'global_init_techs_count': global_init_techs_count,
        'global_init_techs': global_init_techs,
        'global_init_buildings_count': global_init_buildings_count,
        'global_init_buildings': global_init_buildings,
        'veteran_levels': veteran_levels,
        'veteran_name': veteran_name,
        'power_fact': power_fact,
        'move_bonus': move_bonus,
        'base_raise_chance': base_raise_chance,
        'work_raise_chance': work_raise_chance,
        'background_red': background_red,
        'background_green': background_green,
        'background_blue': background_blue,
    }


def decode_requirement(data: bytes, offset: int) -> Tuple[dict, int]:
    """
    Decode a REQUIREMENT from packet payload (10 bytes).

    Requirements specify conditions that must be met for game elements
    (disasters, buildings, techs, etc.) to be available or active.

    Structure (10 bytes):
    - UINT8 type (universals_n enum - VUT_*)
    - SINT32 value (meaning depends on type)
    - UINT8 range (req_range enum)
    - BOOL8 survives (whether destroyed sources satisfy requirement)
    - BOOL8 present (whether requirement must be present vs absent)
    - BOOL8 quiet (whether to hide from help text)

    Args:
        data: Byte array to read from
        offset: Starting position

    Returns:
        Tuple of (requirement_dict, new_offset)
    """
    req_type, offset = decode_uint8(data, offset)
    value, offset = decode_sint32(data, offset)
    range_val, offset = decode_uint8(data, offset)
    survives, offset = decode_bool(data, offset)
    present, offset = decode_bool(data, offset)
    quiet, offset = decode_bool(data, offset)

    return {
        'type': req_type,
        'value': value,
        'range': range_val,
        'survives': survives,
        'present': present,
        'quiet': quiet
    }, offset


def decode_ruleset_disaster(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_DISASTER (224).

    Disasters are negative random events (fires, plagues, etc.) that can occur
    in cities when requirements are met. One packet is sent per disaster type
    during game initialization.

    WARNING: The actual packet structure does NOT match packets.def!
    Real structure (confirmed from captured packets):
    - UINT8 id (key field - disaster type ID)
    - STRING name (variable-length, null-terminated)
    - STRING rule_name (variable-length, null-terminated)
    - UINT8 reqs_count (number of requirements, 0-255)
    - REQUIREMENT reqs[reqs_count] (variable-length array, 10 bytes each)
    - UINT8 frequency (base probability)
    - BV_DISASTER_EFFECTS effects (1-byte bitvector, 7 bits used)

    BV_DISASTER_EFFECTS bits:
    - Bit 0: DE_DESTROY_BUILDING
    - Bit 1: DE_REDUCE_POP
    - Bit 2: DE_EMPTY_FOODSTOCK
    - Bit 3: DE_EMPTY_PRODSTOCK
    - Bit 4: DE_POLLUTION
    - Bit 5: DE_FALLOUT
    - Bit 6: DE_REDUCE_DESTROY

    This is a non-delta protocol packet - uses manual decoder due to
    complex variable-length REQUIREMENT array.

    Returns:
        Dictionary with decoded fields (id, name, rule_name,
        reqs_count, reqs, frequency, effects)
    """
    offset = 0


    # IMPORTANT: This packet CAN use delta protocol despite packets.def saying "lsend"!
    # First disaster is sent full (no bitvector), subsequent ones use delta protocol.
    # Detect by checking if first byte looks like a plausible disaster_id (>100)
    # or a bitvector (<100)

    first_byte = payload[0]
    uses_delta = first_byte < 100  # Heuristic: disaster IDs are typically >100 for first packet

    if uses_delta:
        # Delta protocol: bitvector, then disaster_id, then conditional fields
        bitvector, offset = decode_uint8(payload, offset)
        disaster_id, offset = decode_uint8(payload, offset)
    else:
        # Full packet: disaster_id first, then all fields
        bitvector = 0xFF  # All bits set (all fields present)
        disaster_id, offset = decode_uint8(payload, offset)

    # Helper to check if bit is set in bitvector
    def has_field(bit_index):
        return bool(bitvector & (1 << bit_index))

    # Initialize with defaults
    name = ""
    rule_name = ""
    reqs_count = 0
    reqs = []
    frequency = 0
    effects_byte = 0

    # Conditional fields based on bitvector
    # Bit 0: name
    if has_field(0):
        name, offset = decode_string(payload, offset)

    # Bit 1: rule_name
    if has_field(1):
        rule_name, offset = decode_string(payload, offset)

    # Bit 2: reqs_count
    if has_field(2):
        reqs_count, offset = decode_uint8(payload, offset)

    # Bit 3: reqs array
    if has_field(3):
        for i in range(reqs_count):
            req, offset = decode_requirement(payload, offset)
            reqs.append(req)

    # Bit 4: frequency
    if has_field(4):
        frequency, offset = decode_uint8(payload, offset)

    # Bit 5: unused/reserved?

    # Bit 6: effects
    if has_field(6):
        effects_byte = payload[offset]
        offset += 1

    return {
        'id': disaster_id,
        'name': name,
        'rule_name': rule_name,
        'reqs_count': reqs_count,
        'reqs': reqs,
        'frequency': frequency,
        'effects': effects_byte
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
    elif type_name == 'SINT8':
        return decode_sint8(data, offset)
    elif type_name == 'UINT32':
        return decode_uint32(data, offset)
    elif type_name == 'UINT16':
        return decode_uint16(data, offset)
    elif type_name == 'UINT8':
        return decode_uint8(data, offset)
    elif type_name == 'BOOL':
        return decode_bool(data, offset)
    else:
        raise ValueError(f"Unsupported field type: {type_name}")


def decode_array_diff(
    data: bytes,
    offset: int,
    element_type: str,
    array_size: int,
    cached_array: list = None
) -> Tuple[list, int]:
    """
    Decode an array transmitted using array-diff optimization.

    Array-diff is a bandwidth optimization where only changed array elements
    are transmitted as (index, value) pairs. The end of the list is marked
    by a sentinel index equal to array_size.

    Wire format:
        [index1, value1, index2, value2, ..., sentinel_index]

    Index encoding:
        - 8-bit (uint8) if array_size <= 255
        - 16-bit (uint16) if array_size > 255

    Args:
        data: Payload bytes
        offset: Current offset in the payload
        element_type: Type of array elements ('BOOL', 'SINT32', 'PLAYER', etc.)
        array_size: Maximum array size (also used as sentinel value)
        cached_array: Previously cached array (or None for first transmission)

    Returns:
        Tuple of (decoded_array, new_offset)

    Raises:
        ValueError: If index is out of bounds or invalid

    Algorithm:
        1. Initialize result array from cache (or zeros/defaults if no cache)
        2. Loop reading (index, value) pairs:
           - Read index (uint8 or uint16 based on array_size)
           - If index == array_size: break (sentinel reached)
           - If index > array_size: error (invalid index)
           - Read value and update result[index]
        3. Return updated array
    """
    # Determine index width based on array size
    use_uint16_indices = array_size > 255

    # Initialize result array from cache or defaults
    if cached_array is not None and len(cached_array) == array_size:
        result = cached_array.copy()
    else:
        # No cache or wrong size - initialize with default values
        if element_type == 'BOOL':
            result = [False] * array_size
        elif element_type in ('SINT8', 'SINT16', 'SINT32', 'PLAYER'):
            result = [0] * array_size
        elif element_type in ('UINT8', 'UINT16', 'UINT32'):
            result = [0] * array_size
        else:
            result = [None] * array_size

    # Read (index, value) pairs until sentinel
    while True:
        # Read index
        if use_uint16_indices:
            index, offset = decode_uint16(data, offset)
        else:
            index, offset = decode_uint8(data, offset)

        # Check for sentinel (index == array_size)
        if index == array_size:
            break

        # Validate index
        if index > array_size:
            raise ValueError(
                f"Array-diff index {index} exceeds array size {array_size}"
            )

        # Read value for this index
        value, offset = _decode_field(data, offset, element_type)
        result[index] = value

    return result, offset


def decode_delta_packet(
    payload: bytes,
    packet_spec: PacketSpec,
    delta_cache: 'DeltaCache'
) -> dict:
    """
    Generic delta decoder for any packet with delta support.

    This decoder implements FreeCiv's delta protocol:
    1. Read bitvector indicating which non-key fields are present
    2. Read key fields (always present, transmitted after bitvector)
    3. For each non-key field:
       - If bit is set: read new value from payload
       - If bit is clear: use cached value from previous packet
    4. Update cache with complete packet

    IMPORTANT: FreeCiv transmits bitvector BEFORE key fields (confirmed in
    common/generate_packets.py lines 2267-2282). Key fields are always present
    but come after the bitvector.

    Args:
        payload: Raw packet payload (after header)
        packet_spec: Packet specification from PACKET_SPECS
        delta_cache: Delta cache instance for this connection

    Returns:
        Complete field dictionary with all values (from payload or cache)
    """
    offset = 0
    fields = {}

    # Step 1: Read bitvector FIRST (if packet has non-key fields)
    if packet_spec.num_bitvector_bits > 0:
        bitvector, offset = read_bitvector(
            payload, offset, packet_spec.num_bitvector_bits
        )
    else:
        bitvector = 0

    # Step 2: Read key fields SECOND (always present, always transmitted)
    key_values = []
    for field_spec in packet_spec.key_fields:
        value, offset = _decode_field(payload, offset, field_spec.type_name)
        fields[field_spec.name] = value
        key_values.append(value)

    key_tuple = tuple(key_values)

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
            # Field has changed - read new value from payload
            if field_spec.is_array and field_spec.array_diff:
                # Array with diff optimization - only changed elements transmitted
                cached_array = cached.get(field_spec.name, None)
                value, offset = decode_array_diff(
                    payload, offset,
                    field_spec.element_type,
                    field_spec.array_size,
                    cached_array
                )
            else:
                # Regular field or full array transmission
                value, offset = _decode_field(payload, offset, field_spec.type_name)
            fields[field_spec.name] = value
        else:
            # Field unchanged - use cached value
            fields[field_spec.name] = cached[field_spec.name]

    # Step 5: Update cache with complete packet
    delta_cache.update_cache(packet_spec.packet_type, key_tuple, fields)

    return fields
