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
PACKET_RULESET_SPECIALIST = 142
PACKET_RULESET_DISASTER = 224
PACKET_RULESET_TRADE = 227
PACKET_RULESET_ACHIEVEMENT = 233
PACKET_RULESET_TECH_FLAG = 234
PACKET_RULESET_ACTION_ENABLER = 235
PACKET_RULESET_EXTRA_FLAG = 226
PACKET_RULESET_ACTION = 246
PACKET_RULESET_ACTION_AUTO = 252
PACKET_RULESET_TECH = 144
PACKET_RULESET_GOVERNMENT = 145
PACKET_RULESET_GOVERNMENT_RULER_TITLE = 143
PACKET_RULESET_UNIT_CLASS = 152
PACKET_RULESET_BASE = 153
PACKET_RULESET_ROAD = 220
PACKET_RULESET_UNIT_CLASS_FLAG = 230
PACKET_RULESET_UNIT_FLAG = 229
PACKET_RULESET_UNIT_BONUS = 228
PACKET_RULESET_UNIT = 140
PACKET_RULESET_EXTRA = 232
PACKET_RULESET_GOODS = 248
PACKET_RULESET_RESOURCE = 177
PACKET_RULESET_TERRAIN_CONTROL = 146
PACKET_RULESET_TERRAIN_FLAG = 231
PACKET_RULESET_TERRAIN = 151
PACKET_RULESET_IMPR_FLAG = 20
PACKET_RULESET_BUILDING = 150

# FreeCiv constants
O_LAST = (
    6  # Output types: FOOD, SHIELD, TRADE, GOLD, LUXURY, SCIENCE (from freeciv/common/fc_types.h)
)

# Version constants
MAJOR_VERSION = 3
MINOR_VERSION = 2
PATCH_VERSION = 2
VERSION_LABEL = ""
CAPABILITY = "+Freeciv-3.2-network ownernull16 unignoresync tu32 hap2clnt"

# Compression constants (from freeciv/common/networking/packets.c:53,58,63)
COMPRESSION_BORDER = 16385  # 16*1024 + 1 - packets >= this size are compressed
JUMBO_SIZE = 65535  # 0xffff - marker for jumbo packets
JUMBO_BORDER = 49150  # 64*1024 - COMPRESSION_BORDER - 1

# Compression-related packet types
PACKET_FREEZE_CLIENT = 130  # Start compression grouping
PACKET_THAW_CLIENT = 131  # End compression grouping


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


async def _parse_packet_buffer(buffer: bytes, use_two_byte_type: bool) -> list:
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
        packet_length = struct.unpack(">H", buffer[offset : offset + 2])[0]

        # Read type field (1 or 2 bytes)
        if use_two_byte_type:
            header_size = 4
            if len(buffer) - offset < header_size:
                raise ValueError(f"Incomplete 2-byte type header at offset {offset}")
            packet_type = struct.unpack(">H", buffer[offset + 2 : offset + 4])[0]
        else:
            header_size = 3
            packet_type = struct.unpack("B", buffer[offset + 2 : offset + 3])[0]

        # Validate length
        if packet_length < header_size:
            raise ValueError(f"Invalid packet length {packet_length} at offset {offset}")

        # Check if complete packet available
        if offset + packet_length > len(buffer):
            raise ValueError(
                f"Incomplete packet at offset {offset}: "
                f"need {packet_length} bytes, have {len(buffer) - offset}"
            )

        # Extract payload and raw packet
        payload_start = offset + header_size
        payload_length = packet_length - header_size
        payload = buffer[payload_start : payload_start + payload_length]
        raw_packet = buffer[offset : offset + packet_length]

        packets.append((packet_type, payload, raw_packet))
        offset += packet_length

    return packets


# Data type encoding functions


def encode_string(value: str) -> bytes:
    """Encode a STRING as null-terminated UTF-8 bytes."""
    return value.encode("utf-8") + b"\x00"


def encode_bool(value: bool) -> bytes:
    """Encode a BOOL as a single byte (0 or 1)."""
    return struct.pack("B", 1 if value else 0)


def encode_uint32(value: int) -> bytes:
    """Encode a UINT32 as 4 bytes in big-endian format."""
    return struct.pack(">I", value)


def encode_sint16(value: int) -> bytes:
    """Encode a SINT16 as 2 bytes in big-endian format."""
    return struct.pack(">h", value)


def encode_uint8(value: int) -> bytes:
    """Encode a UINT8 as 1 byte."""
    return struct.pack("B", value)


def encode_sint8(value: int) -> bytes:
    """Encode a SINT8 as 1 byte (signed)."""
    return struct.pack("b", value)


# Data type decoding functions


def decode_string(data: bytes, offset: int) -> Tuple[str, int]:
    """
    Decode a null-terminated STRING from bytes.

    Returns:
        Tuple of (string_value, new_offset)
    """
    end = data.find(b"\x00", offset)
    if end == -1:
        raise ValueError("Null terminator not found in string")
    string = data[offset:end].decode("utf-8")
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
    chunk = data[offset : offset + size]
    # Find null terminator within the fixed-size chunk
    end = chunk.find(b"\x00")
    if end == -1:
        # No null terminator, use entire chunk
        string = chunk.decode("utf-8")
    else:
        # Decode up to null terminator
        string = chunk[:end].decode("utf-8")
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
    value = struct.unpack("b", bytes([data[offset]]))[0]
    return value, offset + 1


def decode_uint32(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode a UINT32 from bytes (big-endian).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack(">I", data[offset : offset + 4])[0]
    return value, offset + 4


def decode_sint16(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode SINT16 (big-endian signed 16-bit).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack(">h", data[offset : offset + 2])[0]
    return value, offset + 2


def decode_uint16(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode UINT16 (big-endian unsigned 16-bit).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack(">H", data[offset : offset + 2])[0]
    return value, offset + 2


def decode_sint32(data: bytes, offset: int) -> Tuple[int, int]:
    """
    Decode SINT32 (big-endian signed 32-bit).

    Returns:
        Tuple of (int_value, new_offset)
    """
    value = struct.unpack(">i", data[offset : offset + 4])[0]
    return value, offset + 4


def decode_ufloat(data: bytes, offset: int, factor: int) -> Tuple[float, int]:
    """
    Decode UFLOAT (unsigned float encoded as UINT16 with scaling factor).

    FreeCiv encodes floats as integers: wire_value = int(float_value * factor)
    Decode: float_value = wire_value / factor

    Args:
        data: Byte array to read from
        offset: Starting position
        factor: Scaling factor (100 for UFLOAT10x3, 10000 for UFLOAT)

    Returns:
        Tuple of (float_value, new_offset)
    """
    uint_value, offset = decode_uint16(data, offset)
    float_value = float(uint_value) / factor
    return float_value, offset


def encode_packet(packet_type: int, payload: bytes) -> bytes:
    """
    Encode a packet with a header.
    """
    packet_length = len(payload) + 3  # 2 bytes length + 1 byte type + payload
    length_header = struct.pack(">H", packet_length)
    return length_header + struct.pack("B", packet_type) + payload


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
    payload = (
        encode_string(username)
        + encode_string(CAPABILITY)
        + encode_string(VERSION_LABEL)
        + encode_uint32(MAJOR_VERSION)
        + encode_uint32(MINOR_VERSION)
        + encode_uint32(PATCH_VERSION)
    )

    # Build complete packet with header
    return encode_packet(PACKET_SERVER_JOIN_REQ, payload)


async def read_packet(
    reader: asyncio.StreamReader, use_two_byte_type: bool = False, validate: bool = False
) -> Tuple[int, bytes, bytes]:
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
    packet_length = struct.unpack(">H", length_bytes)[0]

    if validate:
        print(f"[VALIDATE] Length header: {packet_length} bytes")

    # ============================================================================
    # COMPRESSION DETECTION AND HANDLING
    # ============================================================================

    # Check for JUMBO compressed packet
    if packet_length == JUMBO_SIZE:
        # Read 4-byte actual length (big-endian)
        jumbo_length_bytes = await _recv_exact(reader, 4)
        actual_length = struct.unpack(">I", jumbo_length_bytes)[0]

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
        packet_type = struct.unpack(">H", type_bytes)[0]
        header_size = 4  # 2 bytes length + 2 bytes type
    else:
        type_bytes = await _recv_exact(reader, 1)
        packet_type = struct.unpack("B", type_bytes)[0]
        header_size = 3  # 2 bytes length + 1 byte type

    if validate:
        print(f"[VALIDATE] Type field: {len(type_bytes)} bytes (packet type {packet_type})")

    # Read remaining payload
    payload_length = packet_length - header_size
    payload = await _recv_exact(reader, payload_length) if payload_length > 0 else b""

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
        "you_can_join": you_can_join,
        "message": message,
        "capability": capability,
        "challenge_file": challenge_file,
        "conn_id": conn_id,
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
        "version_label": version_label,
        "major_version": major_version,
        "minor_version": minor_version,
        "patch_version": patch_version,
        "emerg_version": emerg_version,
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
        "message": message,
        "tile": tile,
        "event": event,
        "turn": turn,
        "phase": phase,
        "conn_id": conn_id,
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

    return {"text": text}


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

    return {"text": text}


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

    return {"nsets": nsets, "names": names, "rule_names": rule_names, "descriptions": descriptions}


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

    return {"ngroups": ngroups, "groups": groups, "hidden": hidden}


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
    bitvector = int.from_bytes(payload[offset : offset + 3], byteorder="little")
    offset += 3

    # Read key field (id) SECOND - always present after bitvector
    nation_id, offset = decode_sint16(payload, offset)

    # Initialize result with key field
    result = {"id": nation_id}

    # Helper to check if bit is set
    def has_field(bit_index):
        return bool(bitvector & (1 << bit_index))

    # Initialize all fields with defaults
    result.update(
        {
            "translation_domain": "",
            "adjective": "",
            "rule_name": "",
            "noun_plural": "",
            "graphic_str": "",
            "graphic_alt": "",
            "legend": "",
            "style": 0,
            "leader_count": 0,
            "leader_name": [],
            "leader_is_male": [],
            "is_playable": False,
            "barbarian_type": 0,
            "nsets": 0,
            "sets": [],
            "ngroups": 0,
            "groups": [],
            "init_government_id": -1,
            "init_techs_count": 0,
            "init_techs": [],
            "init_units_count": 0,
            "init_units": [],
            "init_buildings_count": 0,
            "init_buildings": [],
        }
    )

    # Read ONLY the fields indicated by the bitvector

    if has_field(0):  # translation_domain
        result["translation_domain"], offset = decode_string(payload, offset)

    if has_field(1):  # adjective
        result["adjective"], offset = decode_string(payload, offset)

    if has_field(2):  # rule_name
        result["rule_name"], offset = decode_string(payload, offset)

    if has_field(3):  # noun_plural
        result["noun_plural"], offset = decode_string(payload, offset)

    if has_field(4):  # graphic_str
        result["graphic_str"], offset = decode_string(payload, offset)

    if has_field(5):  # graphic_alt
        result["graphic_alt"], offset = decode_string(payload, offset)

    if has_field(6):  # legend
        result["legend"], offset = decode_string(payload, offset)

    if has_field(7):  # style
        result["style"], offset = decode_uint8(payload, offset)

    if has_field(8):  # leader_count
        result["leader_count"], offset = decode_uint8(payload, offset)

    if has_field(9):  # leader_name[]
        result["leader_name"] = []
        for i in range(result["leader_count"]):
            name, offset = decode_string(payload, offset)
            result["leader_name"].append(name)

    if has_field(10):  # leader_is_male[] (BOOL array)
        # Note: Arrays of BOOLs transmit each element as a byte in the payload
        # (boolean header folding only applies to standalone BOOL fields)
        result["leader_is_male"] = []
        for i in range(result["leader_count"]):
            is_male, offset = decode_bool(payload, offset)
            result["leader_is_male"].append(is_male)

    # Field 11: is_playable (BOOL) - uses boolean header folding
    # The bitvector bit IS the field value; no payload bytes consumed
    if has_field(11):
        result["is_playable"] = True
    else:
        result["is_playable"] = False

    if has_field(12):  # barbarian_type
        result["barbarian_type"], offset = decode_uint8(payload, offset)

    if has_field(13):  # nsets
        result["nsets"], offset = decode_uint8(payload, offset)

    if has_field(14):  # sets[]
        result["sets"] = []
        for i in range(result["nsets"]):
            set_id, offset = decode_uint8(payload, offset)
            result["sets"].append(set_id)

    if has_field(15):  # ngroups
        result["ngroups"], offset = decode_uint8(payload, offset)

    if has_field(16):  # groups[]
        result["groups"] = []
        for i in range(result["ngroups"]):
            group_id, offset = decode_uint8(payload, offset)
            result["groups"].append(group_id)

    if has_field(17):  # init_government_id
        result["init_government_id"], offset = decode_sint8(payload, offset)

    if has_field(18):  # init_techs_count
        result["init_techs_count"], offset = decode_uint8(payload, offset)

    if has_field(19):  # init_techs[]
        result["init_techs"] = []
        for i in range(result["init_techs_count"]):
            tech_id, offset = decode_uint16(payload, offset)
            result["init_techs"].append(tech_id)

    if has_field(20):  # init_units_count
        result["init_units_count"], offset = decode_uint8(payload, offset)

    if has_field(21):  # init_units[]
        result["init_units"] = []
        for i in range(result["init_units_count"]):
            unit_id, offset = decode_uint16(payload, offset)
            result["init_units"].append(unit_id)

    if has_field(22):  # init_buildings_count
        result["init_buildings_count"], offset = decode_uint8(payload, offset)

    if has_field(23):  # init_buildings[]
        result["init_buildings"] = []
        for i in range(result["init_buildings_count"]):
            building_id, offset = decode_uint8(payload, offset)
            result["init_buildings"].append(building_id)

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
    result = {"ncount": 0, "is_pickable": [], "nationset_change": False}

    # Field 0: ncount (UINT16, big-endian)
    if bitvector & (1 << 0):
        # Note: FreeCiv uses big-endian for multi-byte integers (consistent with rest of protocol)
        ncount = int.from_bytes(payload[offset : offset + 2], byteorder="big")
        offset += 2
        result["ncount"] = ncount

    # Field 1: is_pickable (BOOL array)
    if bitvector & (1 << 1):
        ncount = result["ncount"]
        is_pickable = []
        for i in range(ncount):
            pickable = bool(payload[offset])
            is_pickable.append(pickable)
            offset += 1
        result["is_pickable"] = is_pickable

    # Field 2: nationset_change (BOOL, folded into bitvector)
    # Boolean header folding: the bitvector bit IS the field value
    # No payload bytes consumed for this field
    result["nationset_change"] = bool(bitvector & (1 << 2))

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
        "default_specialist": default_specialist,
        "global_init_techs_count": global_init_techs_count,
        "global_init_techs": global_init_techs,
        "global_init_buildings_count": global_init_buildings_count,
        "global_init_buildings": global_init_buildings,
        "veteran_levels": veteran_levels,
        "veteran_name": veteran_name,
        "power_fact": power_fact,
        "move_bonus": move_bonus,
        "base_raise_chance": base_raise_chance,
        "work_raise_chance": work_raise_chance,
        "background_red": background_red,
        "background_green": background_green,
        "background_blue": background_blue,
    }


def decode_ruleset_specialist(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_SPECIALIST (142) using delta protocol.

    Transmits specialist type definitions (e.g., scientists, entertainers,
    taxmen). Specialists are special citizen types that work in cities to
    provide bonuses instead of working terrain tiles.

    Uses delta protocol with 9 conditional fields and variable-length
    requirements array. Cache key is empty tuple (hash_const).

    Reference: freeciv-build/packets_gen.c:51261

    Structure (based on actual packet observation):
    - Bitvector byte 0 (UINT8) - indicates which fields 1-8 are present
    - Byte 1: id (UINT8) - Specialist type ID (always present)
    - Field 1: plural_name (STRING) - Display name (plural)
    - Field 2: rule_name (STRING) - Internal identifier
    - Field 3: short_name (STRING) - Abbreviated display name
    - Field 4: graphic_str (STRING) - Primary graphic tag
    - Field 5: graphic_alt (STRING) - Alternate graphic tag
    - Field 6: reqs_count (UINT8) - Number of requirements
    - Field 7: reqs (REQUIREMENT array, length from reqs_count)
    - Field 8: helptext (STRING) - Help text description

    Args:
        payload: Raw packet bytes (header already stripped)
        delta_cache: Delta protocol cache

    Returns:
        Dictionary with decoded specialist fields
    """
    offset = 0

    # Read bitvector (9 fields, need 2 bytes)
    bitvector, offset = read_bitvector(payload, offset, 9)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_SPECIALIST, ())

    # Initialize from cache or defaults
    if cached:
        specialist_id = cached.get("id", 0)
        plural_name = cached.get("plural_name", "")
        rule_name = cached.get("rule_name", "")
        short_name = cached.get("short_name", "")
        graphic_str = cached.get("graphic_str", "")
        graphic_alt = cached.get("graphic_alt", "")
        reqs_count = cached.get("reqs_count", 0)
        reqs = cached.get("reqs", []).copy()
        helptext = cached.get("helptext", "")
    else:
        specialist_id = 0
        plural_name = ""
        rule_name = ""
        short_name = ""
        graphic_str = ""
        graphic_alt = ""
        reqs_count = 0
        reqs = []
        helptext = ""

    # Decode conditional fields based on bitvector
    # Bit 0: id (UINT8)
    if is_bit_set(bitvector, 0):
        specialist_id, offset = decode_uint8(payload, offset)

    # Bit 1: plural_name (STRING)
    if is_bit_set(bitvector, 1):
        plural_name, offset = decode_string(payload, offset)

    # Bit 2: rule_name (STRING)
    if is_bit_set(bitvector, 2):
        rule_name, offset = decode_string(payload, offset)

    # Bit 3: short_name (STRING)
    if is_bit_set(bitvector, 3):
        short_name, offset = decode_string(payload, offset)

    # Bit 4: graphic_str (STRING)
    if is_bit_set(bitvector, 4):
        graphic_str, offset = decode_string(payload, offset)

    # Bit 5: graphic_alt (STRING)
    if is_bit_set(bitvector, 5):
        graphic_alt, offset = decode_string(payload, offset)

    # Bit 6: reqs_count (UINT8)
    if is_bit_set(bitvector, 6):
        reqs_count, offset = decode_uint8(payload, offset)

    # Bit 7: reqs array (REQUIREMENT[], length from reqs_count)
    if is_bit_set(bitvector, 7):
        reqs = []
        for i in range(reqs_count):
            req, offset = decode_requirement(payload, offset)
            reqs.append(req)

    # Bit 8: helptext (STRING)
    if is_bit_set(bitvector, 8):
        helptext, offset = decode_string(payload, offset)

    # Build result
    result = {
        "id": specialist_id,
        "plural_name": plural_name,
        "rule_name": rule_name,
        "short_name": short_name,
        "graphic_str": graphic_str,
        "graphic_alt": graphic_alt,
        "reqs_count": reqs_count,
        "reqs": reqs,
        "helptext": helptext,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_SPECIALIST, (), result)

    return result


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
        "type": req_type,
        "value": value,
        "range": range_val,
        "survives": survives,
        "present": present,
        "quiet": quiet,
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
        "id": disaster_id,
        "name": name,
        "rule_name": rule_name,
        "reqs_count": reqs_count,
        "reqs": reqs,
        "frequency": frequency,
        "effects": effects_byte,
    }


def decode_ruleset_achievement(payload: bytes) -> dict:
    """
    Decode PACKET_RULESET_ACHIEVEMENT (233).

    WARNING: packets.def is WRONG - there is NO 'value' field in real packets!

    Real structure (verified from captured packet inbound_0599_type233.packet):
    - UINT8 id
    - STRING name
    - STRING rule_name
    - ACHIEVEMENT_TYPE type (UINT8 enum)
    - BOOL unique

    This is a non-delta protocol packet.
    """
    offset = 0

    # Field 1: UINT8 id
    achievement_id, offset = decode_uint8(payload, offset)

    # Field 2: STRING name
    name, offset = decode_string(payload, offset)

    # Field 3: STRING rule_name
    rule_name, offset = decode_string(payload, offset)

    # Field 4: ACHIEVEMENT_TYPE type (UINT8 enum)
    achievement_type, offset = decode_uint8(payload, offset)

    # Field 5: BOOL unique
    unique, offset = decode_bool(payload, offset)

    # NOTE: packets.def incorrectly lists a UINT16 'value' field here.
    # Real server packets do NOT include this field!

    return {
        "id": achievement_id,
        "name": name,
        "rule_name": rule_name,
        "type": achievement_type,
        "unique": unique,
    }


def decode_ruleset_trade(payload: bytes) -> dict:
    """Decode PACKET_RULESET_TRADE (227).

    Trade routes define how cities establish commercial connections.
    Multiple packets sent (one per trade route type) during initialization.

    Uses delta protocol with no key fields - cache is initialized with zeros.
    Fields are transmitted only if different from cached values.

    Wire format:
    - Byte 0: bitvector (4 bits used for 4 fields)
    - Conditional fields based on bitvector:
      - Bit 0 set: UINT8 id
      - Bit 1 set: UINT16 trade_pct (big-endian)
      - Bit 2 set: UINT8 cancelling
      - Bit 3 set: UINT8 bonus_type

    Enum values:
    - cancelling: 0=Active, 1=Inactive, 2=Cancel
    - bonus_type: 0=None, 1=Gold, 2=Science, 3=Both
    """
    offset = 0

    # Read bitvector
    bitvector, offset = decode_uint8(payload, offset)

    # Helper to check if bit is set
    def has_field(bit_index):
        return bool(bitvector & (1 << bit_index))

    # Initialize with defaults (cache starts at zero for packets with no key fields)
    trade_id = 0
    trade_pct = 0
    cancelling = 0
    bonus_type = 0

    # Conditional fields based on bitvector
    # Bit 0: id
    if has_field(0):
        trade_id, offset = decode_uint8(payload, offset)

    # Bit 1: trade_pct
    if has_field(1):
        trade_pct, offset = decode_uint16(payload, offset)

    # Bit 2: cancelling
    if has_field(2):
        cancelling, offset = decode_uint8(payload, offset)

    # Bit 3: bonus_type
    if has_field(3):
        bonus_type, offset = decode_uint8(payload, offset)

    return {
        "id": trade_id,
        "trade_pct": trade_pct,
        "cancelling": cancelling,
        "bonus_type": bonus_type,
    }


def decode_ruleset_resource(payload: bytes) -> dict:
    """Decode PACKET_RULESET_RESOURCE (177).

    Resources define tile bonuses (Gold, Wheat, Horses, etc.) with output values
    for the 6 output types: Food, Shield, Trade, Gold, Luxury, and Science.

    Uses delta protocol with no key fields - cache is initialized with zeros.
    Fields are transmitted only if different from cached values.

    Wire format:
    - Byte 0: bitvector (2 bits used for 2 fields)
    - Conditional fields based on bitvector:
      - Bit 0 set: UINT8 id
      - Bit 1 set: UINT8[6] output array (6 bytes, one per output type)

    Output indices: [0=FOOD, 1=SHIELD, 2=TRADE, 3=GOLD, 4=LUXURY, 5=SCIENCE]

    Reference: freeciv-build/packets_gen.c:79305
    """
    offset = 0

    # Read bitvector
    bitvector, offset = decode_uint8(payload, offset)

    # Helper to check if bit is set
    def has_field(bit_index):
        return bool(bitvector & (1 << bit_index))

    # Initialize with defaults (cache starts at zero for packets with no key fields)
    resource_id = 0
    output = [0] * O_LAST  # O_LAST=6

    # Conditional fields based on bitvector
    # Bit 0: id
    if has_field(0):
        resource_id, offset = decode_uint8(payload, offset)

    # Bit 1: output array (6 bytes)
    if has_field(1):
        output = []
        for i in range(O_LAST):
            value, offset = decode_uint8(payload, offset)
            output.append(value)

    return {"id": resource_id, "output": output}


def decode_ruleset_action(payload: bytes) -> dict:
    """Decode PACKET_RULESET_ACTION (246).

    Actions define what units can do (establish embassy, trade, attack, etc.).
    Multiple packets sent (one per action type) during initialization.

    Uses delta protocol with all fields conditional (cache keyed by action ID).

    Wire format:
    - Bytes 0-1: bitvector (12 bits, little-endian)
    - Conditional fields based on bitvector:
      - Bit 0: UINT8 id
      - Bit 1: STRING ui_name
      - Bit 2: BOOL quiet (header-folded, NO payload)
      - Bit 3: UINT8 result
      - Bit 4: BITVECTOR sub_results (1 byte, 4 bits)
      - Bit 5: BOOL actor_consuming_always (header-folded, NO payload)
      - Bit 6: UINT8 act_kind
      - Bit 7: UINT8 tgt_kind
      - Bit 8: UINT8 sub_tgt_kind
      - Bit 9: SINT32 min_distance
      - Bit 10: SINT32 max_distance
      - Bit 11: BITVECTOR blocked_by (16 bytes, 128 bits for 125 actions)

    Reference: freeciv-build/packets_gen.c:68608
    """
    offset = 0

    # Read bitvector (12 bits = 2 bytes)
    bitvector, offset = read_bitvector(payload, offset, 12)

    # Helper to check if bit is set
    def has_field(bit_index):
        return bool(bitvector & (1 << bit_index))

    # Initialize with defaults (delta protocol cache)
    action_id = 0
    ui_name = ""
    quiet = False
    result = 0
    sub_results = 0
    actor_consuming_always = False
    act_kind = 0
    tgt_kind = 0
    sub_tgt_kind = 0
    min_distance = 0
    max_distance = 0
    blocked_by = 0

    # Conditional fields based on bitvector
    # Bit 0: id
    if has_field(0):
        action_id, offset = decode_uint8(payload, offset)

    # Bit 1: ui_name
    if has_field(1):
        ui_name, offset = decode_string(payload, offset)

    # Bit 2: quiet (HEADER-FOLDED - no payload bytes!)
    quiet = has_field(2)

    # Bit 3: result
    if has_field(3):
        result, offset = decode_uint8(payload, offset)

    # Bit 4: sub_results (bitvector, 4 bits = 1 byte)
    if has_field(4):
        sub_results, offset = read_bitvector(payload, offset, 4)

    # Bit 5: actor_consuming_always (HEADER-FOLDED - no payload bytes!)
    actor_consuming_always = has_field(5)

    # Bit 6: act_kind
    if has_field(6):
        act_kind, offset = decode_uint8(payload, offset)

    # Bit 7: tgt_kind
    if has_field(7):
        tgt_kind, offset = decode_uint8(payload, offset)

    # Bit 8: sub_tgt_kind
    if has_field(8):
        sub_tgt_kind, offset = decode_uint8(payload, offset)

    # Bit 9: min_distance
    if has_field(9):
        min_distance, offset = decode_sint32(payload, offset)

    # Bit 10: max_distance
    if has_field(10):
        max_distance, offset = decode_sint32(payload, offset)

    # Bit 11: blocked_by (bitvector, 128 bits for 125 actions = 16 bytes)
    if has_field(11):
        blocked_by, offset = read_bitvector(payload, offset, 128)

    return {
        "id": action_id,
        "ui_name": ui_name,
        "quiet": quiet,
        "result": result,
        "sub_results": sub_results,
        "actor_consuming_always": actor_consuming_always,
        "act_kind": act_kind,
        "tgt_kind": tgt_kind,
        "sub_tgt_kind": sub_tgt_kind,
        "min_distance": min_distance,
        "max_distance": max_distance,
        "blocked_by": blocked_by,
    }


def decode_ruleset_action_enabler(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_ACTION_ENABLER (235).

    Action enablers define conditions for when game actions can be performed.
    Each enabler specifies requirements for the actor (unit/city/player) and
    target (recipient of action).

    Structure (from freeciv-build/packets_gen.c:69222):
    - 1-byte bitvector (5 bits used)
    - Bit 0: enabled_action (UINT8) - Action ID
    - Bit 1: actor_reqs_count (UINT8) - Number of actor requirements
    - Bit 2: actor_reqs (REQUIREMENT array) - Requirements for actor
    - Bit 3: target_reqs_count (UINT8) - Number of target requirements
    - Bit 4: target_reqs (REQUIREMENT array) - Requirements for target

    Cache behavior: Uses hash_const - all packets share same cache entry (no key fields).

    Args:
        payload: Raw packet bytes (after packet header)
        delta_cache: Delta cache for retrieving cached field values

    Returns:
        Dictionary with decoded fields
    """
    offset = 0

    # Read 5-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 5)

    # Helper to check if field is present
    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_ACTION_ENABLER, ())

    # Initialize from cache or defaults
    if cached:
        enabled_action = cached.get("enabled_action", 0)
        actor_reqs_count = cached.get("actor_reqs_count", 0)
        actor_reqs = cached.get("actor_reqs", []).copy()
        target_reqs_count = cached.get("target_reqs_count", 0)
        target_reqs = cached.get("target_reqs", []).copy()
    else:
        enabled_action = 0
        actor_reqs_count = 0
        actor_reqs = []
        target_reqs_count = 0
        target_reqs = []

    # Bit 0: enabled_action
    if has_field(0):
        enabled_action, offset = decode_uint8(payload, offset)

    # Bit 1: actor_reqs_count
    if has_field(1):
        actor_reqs_count, offset = decode_uint8(payload, offset)

    # Bit 2: actor_reqs (array of REQUIREMENT, each 10 bytes)
    # Uses current actor_reqs_count (from cache or just read)
    if has_field(2):
        actor_reqs = []
        for _ in range(actor_reqs_count):
            req, offset = decode_requirement(payload, offset)
            actor_reqs.append(req)

    # Bit 3: target_reqs_count
    if has_field(3):
        target_reqs_count, offset = decode_uint8(payload, offset)

    # Bit 4: target_reqs (array of REQUIREMENT, each 10 bytes)
    # Uses current target_reqs_count (from cache or just read)
    if has_field(4):
        target_reqs = []
        for _ in range(target_reqs_count):
            req, offset = decode_requirement(payload, offset)
            target_reqs.append(req)

    # Build result
    result = {
        "enabled_action": enabled_action,
        "actor_reqs_count": actor_reqs_count,
        "actor_reqs": actor_reqs,
        "target_reqs_count": target_reqs_count,
        "target_reqs": target_reqs,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_ACTION_ENABLER, (), result)

    return result


def decode_ruleset_action_auto(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_ACTION_AUTO (252).

    Defines rules for automatically performing actions when specific triggers occur,
    without player input (e.g., disbanding unit on upkeep failure, auto-attack when
    moving adjacent to enemy).

    Structure (from freeciv-build/packets_gen.c:69769):
    - 1-byte bitvector (6 bits used)
    - Bit 0: id (UINT8) - Auto action configuration ID
    - Bit 1: cause (UINT8) - Trigger cause enum (AAPC_*)
    - Bit 2: reqs_count (UINT8) - Number of requirements
    - Bit 3: reqs (REQUIREMENT array) - Requirements that must be met
    - Bit 4: alternatives_count (UINT8) - Number of alternative actions
    - Bit 5: alternatives (ACTION_ID array, UINT8 each) - Alternative action IDs

    Cache behavior: Uses hash_const - all packets share same cache entry (no key fields).

    Args:
        payload: Raw packet bytes (after packet header)
        delta_cache: Delta cache for retrieving cached field values

    Returns:
        Dictionary with decoded fields
    """
    offset = 0

    # Read 6-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 6)

    # Helper to check if field is present
    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_ACTION_AUTO, ())

    # Initialize from cache or defaults
    if cached:
        id = cached.get("id", 0)
        cause = cached.get("cause", 0)
        reqs_count = cached.get("reqs_count", 0)
        reqs = cached.get("reqs", []).copy()
        alternatives_count = cached.get("alternatives_count", 0)
        alternatives = cached.get("alternatives", []).copy()
    else:
        id = 0
        cause = 0
        reqs_count = 0
        reqs = []
        alternatives_count = 0
        alternatives = []

    # Bit 0: id
    if has_field(0):
        id, offset = decode_uint8(payload, offset)

    # Bit 1: cause
    if has_field(1):
        cause, offset = decode_uint8(payload, offset)

    # Bit 2: reqs_count
    if has_field(2):
        reqs_count, offset = decode_uint8(payload, offset)

    # Bit 3: reqs (array of REQUIREMENT, each 10 bytes)
    # Uses current reqs_count (from cache or just read)
    if has_field(3):
        reqs = []
        for _ in range(reqs_count):
            req, offset = decode_requirement(payload, offset)
            reqs.append(req)

    # Bit 4: alternatives_count
    if has_field(4):
        alternatives_count, offset = decode_uint8(payload, offset)

    # Bit 5: alternatives (array of ACTION_ID, each UINT8)
    # Uses current alternatives_count (from cache or just read)
    if has_field(5):
        alternatives = []
        for _ in range(alternatives_count):
            action_id, offset = decode_uint8(payload, offset)
            alternatives.append(action_id)

    # Build result
    result = {
        "id": id,
        "cause": cause,
        "reqs_count": reqs_count,
        "reqs": reqs,
        "alternatives_count": alternatives_count,
        "alternatives": alternatives,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_ACTION_AUTO, (), result)

    return result


def decode_ruleset_tech_flag(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_TECH_FLAG (234).

    Technology flags are properties that can be assigned to technologies
    in the ruleset to define game mechanics and requirements.

    Structure (from freeciv-build/packets_gen.c:53225):
    - 1-byte bitvector (3 bits used)
    - Bit 0: id (UINT8) - Technology flag identifier
    - Bit 1: name (STRING) - Flag name
    - Bit 2: helptxt (STRING) - Help text

    Cache behavior: Uses hash_const - all packets share same cache entry (no key fields).

    Args:
        payload: Raw packet bytes (after packet header)
        delta_cache: Delta cache for retrieving cached field values

    Returns:
        Dictionary with decoded fields: id, name, helptxt
    """
    offset = 0

    # Read 3-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 3)

    # Helper to check if field is present
    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_TECH_FLAG, ())

    # Initialize from cache or defaults
    if cached:
        tech_id = cached.get("id", 0)
        name = cached.get("name", "")
        helptxt = cached.get("helptxt", "")
    else:
        tech_id = 0
        name = ""
        helptxt = ""

    # Bit 0: id
    if has_field(0):
        tech_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if has_field(1):
        name, offset = decode_string(payload, offset)

    # Bit 2: helptxt
    if has_field(2):
        helptxt, offset = decode_string(payload, offset)

    # Build result
    result = {"id": tech_id, "name": name, "helptxt": helptxt}

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_TECH_FLAG, (), result)

    return result


def decode_ruleset_extra_flag(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_EXTRA_FLAG (226).

    Extra flags are properties that can be assigned to extras (terrain features
    like forests, rivers, bases) in the ruleset to define game mechanics.

    Structure (from freeciv-build/packets_gen.c:65141):
    - 1-byte bitvector (3 bits used)
    - Bit 0: id (UINT8) - Extra flag identifier
    - Bit 1: name (STRING) - Flag name
    - Bit 2: helptxt (STRING) - Help text

    Cache behavior: Uses hash_const - all packets share same cache entry (no key fields).

    Args:
        payload: Raw packet bytes (after packet header)
        delta_cache: Delta cache for retrieving cached field values

    Returns:
        Dictionary with decoded fields: id, name, helptxt
    """
    offset = 0

    # Read 3-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 3)

    # Helper to check if field is present
    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_EXTRA_FLAG, ())

    # Initialize from cache or defaults
    if cached:
        extra_id = cached.get("id", 0)
        name = cached.get("name", "")
        helptxt = cached.get("helptxt", "")
    else:
        extra_id = 0
        name = ""
        helptxt = ""

    # Bit 0: id
    if has_field(0):
        extra_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if has_field(1):
        name, offset = decode_string(payload, offset)

    # Bit 2: helptxt
    if has_field(2):
        helptxt, offset = decode_string(payload, offset)

    # Build result
    result = {"id": extra_id, "name": name, "helptxt": helptxt}

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_EXTRA_FLAG, (), result)

    return result


def decode_ruleset_terrain_flag(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_TERRAIN_FLAG (231).

    Structure (from freeciv-build/packets_gen.c:62323):
    - 1-byte bitvector (3 bits used)
    - Bit 0: id (UINT8) - Terrain flag identifier
    - Bit 1: name (STRING) - Flag name
    - Bit 2: helptxt (STRING) - Help text

    Cache behavior: Uses hash_const - all packets share same cache entry (no key fields).
    """
    offset = 0

    # Read 3-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 3)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_TERRAIN_FLAG, ())

    # Initialize from cache or defaults
    if cached:
        terrain_id = cached.get("id", 0)
        name = cached.get("name", "")
        helptxt = cached.get("helptxt", "")
    else:
        terrain_id = 0
        name = ""
        helptxt = ""

    # Bit 0: id
    if is_bit_set(bitvector, 0):
        terrain_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if is_bit_set(bitvector, 1):
        name, offset = decode_string(payload, offset)

    # Bit 2: helptxt
    if is_bit_set(bitvector, 2):
        helptxt, offset = decode_string(payload, offset)

    # Build result
    result = {"id": terrain_id, "name": name, "helptxt": helptxt}

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_TERRAIN_FLAG, (), result)

    return result


def decode_ruleset_impr_flag(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_IMPR_FLAG (20).

    Structure (from freeciv-build/packets_gen.c):
    - 1-byte bitvector (3 bits used)
    - Bit 0: id (UINT8) - Improvement flag identifier
    - Bit 1: name (STRING) - Flag name
    - Bit 2: helptxt (STRING) - Help text

    Cache behavior: Uses hash_const - all packets share same cache entry (no key fields).
    """
    offset = 0

    # Read 3-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 3)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_IMPR_FLAG, ())

    # Initialize from cache or defaults
    if cached:
        impr_id = cached.get("id", 0)
        name = cached.get("name", "")
        helptxt = cached.get("helptxt", "")
    else:
        impr_id = 0
        name = ""
        helptxt = ""

    # Bit 0: id
    if is_bit_set(bitvector, 0):
        impr_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if is_bit_set(bitvector, 1):
        name, offset = decode_string(payload, offset)

    # Bit 2: helptxt
    if is_bit_set(bitvector, 2):
        helptxt, offset = decode_string(payload, offset)

    # Build result
    result = {"id": impr_id, "name": name, "helptxt": helptxt}

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_IMPR_FLAG, (), result)

    return result


def decode_ruleset_unit_class(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_UNIT_CLASS (152) - unit class definition.

    Unit classes define categories of military units (Land, Sea, Air) with
    shared movement and combat properties. Multiple packets sent during
    ruleset initialization (one per unit class).

    Structure from freeciv-build/packets_gen.c:62574:
    - 8-bit bitvector (1 byte) - 8 fields
    - Bit 0: id (UINT8)
    - Bit 1: name (STRING)
    - Bit 2: rule_name (STRING)
    - Bit 3: min_speed (UINT32)
    - Bit 4: hp_loss_pct (UINT8)
    - Bit 5: non_native_def_pct (UINT16)
    - Bit 6: flags (BITVECTOR - 4 bytes for 32 unit class flags)
    - Bit 7: helptext (STRING)
    - Cache: hash_const (all packets share same cache entry)

    Returns:
        Dictionary with decoded fields: id, name, rule_name, min_speed,
        hp_loss_pct, non_native_def_pct, flags, helptext
    """
    offset = 0

    # Read 8-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 8)

    # Helper to check if field is present
    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_UNIT_CLASS, ())

    # Initialize from cache or defaults
    if cached:
        unit_class_id = cached.get("id", 0)
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        min_speed = cached.get("min_speed", 0)
        hp_loss_pct = cached.get("hp_loss_pct", 0)
        non_native_def_pct = cached.get("non_native_def_pct", 0)
        flags = cached.get("flags", 0)
        helptext = cached.get("helptext", "")
    else:
        unit_class_id = 0
        name = ""
        rule_name = ""
        min_speed = 0
        hp_loss_pct = 0
        non_native_def_pct = 0
        flags = 0
        helptext = ""

    # Bit 0: id
    if has_field(0):
        unit_class_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if has_field(1):
        name, offset = decode_string(payload, offset)

    # Bit 2: rule_name
    if has_field(2):
        rule_name, offset = decode_string(payload, offset)

    # Bit 3: min_speed
    if has_field(3):
        min_speed, offset = decode_uint32(payload, offset)

    # Bit 4: hp_loss_pct
    if has_field(4):
        hp_loss_pct, offset = decode_uint8(payload, offset)

    # Bit 5: non_native_def_pct
    if has_field(5):
        non_native_def_pct, offset = decode_uint16(payload, offset)

    # Bit 6: flags (32-bit bitvector, 4 bytes)
    if has_field(6):
        flags, offset = decode_uint32(payload, offset)

    # Bit 7: helptext
    if has_field(7):
        helptext, offset = decode_string(payload, offset)

    # Build result
    result = {
        "id": unit_class_id,
        "name": name,
        "rule_name": rule_name,
        "min_speed": min_speed,
        "hp_loss_pct": hp_loss_pct,
        "non_native_def_pct": non_native_def_pct,
        "flags": flags,
        "helptext": helptext,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_UNIT_CLASS, (), result)

    return result


def decode_ruleset_base(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """Decode PACKET_RULESET_BASE (153) - base type definition."""
    offset = 0

    # Read 6-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 6)

    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_BASE, ())

    # Initialize from cache or defaults
    if cached:
        base_id = cached.get("id", 0)
        gui_type = cached.get("gui_type", 0)
        border_sq = cached.get("border_sq", -1)
        vision_main_sq = cached.get("vision_main_sq", -1)
        vision_invis_sq = cached.get("vision_invis_sq", -1)
        vision_subs_sq = cached.get("vision_subs_sq", -1)
    else:
        base_id = 0
        gui_type = 0
        border_sq = -1
        vision_main_sq = -1
        vision_invis_sq = -1
        vision_subs_sq = -1

    # Decode fields based on bitvector
    if has_field(0):
        base_id, offset = decode_uint8(payload, offset)
    if has_field(1):
        gui_type, offset = decode_uint8(payload, offset)
    if has_field(2):
        border_sq, offset = decode_sint8(payload, offset)
    if has_field(3):
        vision_main_sq, offset = decode_sint8(payload, offset)
    if has_field(4):
        vision_invis_sq, offset = decode_sint8(payload, offset)
    if has_field(5):
        vision_subs_sq, offset = decode_sint8(payload, offset)

    # Build result
    result = {
        "id": base_id,
        "gui_type": gui_type,
        "border_sq": border_sq,
        "vision_main_sq": vision_main_sq,
        "vision_invis_sq": vision_invis_sq,
        "vision_subs_sq": vision_subs_sq,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_BASE, (), result)

    return result


def decode_ruleset_road(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_ROAD (220) - road type definition.

    Structure from freeciv-build/packets_gen.c:65770:
    - 12-bit bitvector (2 bytes)
    - Bit 0: id (UINT8)
    - Bit 1: gui_type (UINT8)
    - Bit 2: first_reqs_count (UINT8)
    - Bit 3: first_reqs (REQUIREMENT array, 10 bytes each)
    - Bit 4: move_cost (SINT16)
    - Bit 5: move_mode (UINT8)
    - Bit 6: tile_incr_const (UINT16[6])
    - Bit 7: tile_incr (UINT16[6])
    - Bit 8: tile_bonus (UINT16[6])
    - Bit 9: compat (UINT8)
    - Bit 10: integrates (BV_MAX_EXTRAS bitvector, 250 bits, 32 bytes)
    - Bit 11: flags (BV_ROAD_FLAGS bitvector, 4 bits, 1 byte)
    - Cache: hash_const (empty tuple)

    Returns:
        Dictionary with road type fields
    """
    offset = 0

    # Read 12-bit bitvector (2 bytes)
    bitvector, offset = read_bitvector(payload, offset, 12)

    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_ROAD, ())

    # Initialize from cache or defaults
    if cached:
        road_id = cached.get("id", 0)
        gui_type = cached.get("gui_type", 0)
        first_reqs_count = cached.get("first_reqs_count", 0)
        first_reqs = cached.get("first_reqs", []).copy()
        move_cost = cached.get("move_cost", 0)
        move_mode = cached.get("move_mode", 0)
        tile_incr_const = cached.get("tile_incr_const", [0] * O_LAST).copy()
        tile_incr = cached.get("tile_incr", [0] * O_LAST).copy()
        tile_bonus = cached.get("tile_bonus", [0] * O_LAST).copy()
        compat = cached.get("compat", 3)  # Default: ROCO_NONE
        integrates = cached.get("integrates", 0)
        flags = cached.get("flags", 0)
    else:
        road_id = 0
        gui_type = 0
        first_reqs_count = 0
        first_reqs = []
        move_cost = 0
        move_mode = 0
        tile_incr_const = [0] * O_LAST
        tile_incr = [0] * O_LAST
        tile_bonus = [0] * O_LAST
        compat = 3  # ROCO_NONE
        integrates = 0
        flags = 0

    # Decode fields based on bitvector
    if has_field(0):
        road_id, offset = decode_uint8(payload, offset)

    if has_field(1):
        gui_type, offset = decode_uint8(payload, offset)

    if has_field(2):
        first_reqs_count, offset = decode_uint8(payload, offset)

    if has_field(3):
        first_reqs = []
        for _ in range(first_reqs_count):
            req, offset = decode_requirement(payload, offset)
            first_reqs.append(req)

    if has_field(4):
        move_cost, offset = decode_sint16(payload, offset)

    if has_field(5):
        move_mode, offset = decode_uint8(payload, offset)

    if has_field(6):
        tile_incr_const = []
        for _ in range(O_LAST):
            val, offset = decode_uint16(payload, offset)
            tile_incr_const.append(val)

    if has_field(7):
        tile_incr = []
        for _ in range(O_LAST):
            val, offset = decode_uint16(payload, offset)
            tile_incr.append(val)

    if has_field(8):
        tile_bonus = []
        for _ in range(O_LAST):
            val, offset = decode_uint16(payload, offset)
            tile_bonus.append(val)

    if has_field(9):
        compat, offset = decode_uint8(payload, offset)

    if has_field(10):
        integrates, offset = read_bitvector(payload, offset, 250)

    if has_field(11):
        flags, offset = read_bitvector(payload, offset, 4)

    # Build result
    result = {
        "id": road_id,
        "gui_type": gui_type,
        "first_reqs_count": first_reqs_count,
        "first_reqs": first_reqs,
        "move_cost": move_cost,
        "move_mode": move_mode,
        "tile_incr_const": tile_incr_const,
        "tile_incr": tile_incr,
        "tile_bonus": tile_bonus,
        "compat": compat,
        "integrates": integrates,
        "flags": flags,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_ROAD, (), result)

    return result


def decode_ruleset_goods(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """Decode PACKET_RULESET_GOODS (248) - trade goods configuration."""
    offset = 0

    # Read 10-bit bitvector (2 bytes) for 10 conditional fields
    bitvector, offset = read_bitvector(payload, offset, 10)

    # Get cached packet (hash_const - empty tuple key)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_GOODS, ())

    # Initialize from cache or defaults
    if cached:
        goods_id = cached.get("id", 0)
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        reqs_count = cached.get("reqs_count", 0)
        reqs = cached.get("reqs", [])
        from_pct = cached.get("from_pct", 0)
        to_pct = cached.get("to_pct", 0)
        onetime_pct = cached.get("onetime_pct", 0)
        flags = cached.get("flags", 0)
        helptext = cached.get("helptext", "")
    else:
        goods_id = 0
        name = ""
        rule_name = ""
        reqs_count = 0
        reqs = []
        from_pct = 0
        to_pct = 0
        onetime_pct = 0
        flags = 0
        helptext = ""

    # Decode conditional fields based on bitvector
    # Bit 0: id
    if is_bit_set(bitvector, 0):
        goods_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if is_bit_set(bitvector, 1):
        name, offset = decode_string(payload, offset)

    # Bit 2: rule_name
    if is_bit_set(bitvector, 2):
        rule_name, offset = decode_string(payload, offset)

    # Bit 3: reqs_count
    if is_bit_set(bitvector, 3):
        reqs_count, offset = decode_uint8(payload, offset)

    # Bit 4: reqs (array of requirements)
    if is_bit_set(bitvector, 4):
        reqs = []
        for _ in range(reqs_count):
            req, offset = decode_requirement(payload, offset)
            reqs.append(req)

    # Bit 5: from_pct
    if is_bit_set(bitvector, 5):
        from_pct, offset = decode_uint16(payload, offset)

    # Bit 6: to_pct
    if is_bit_set(bitvector, 6):
        to_pct, offset = decode_uint16(payload, offset)

    # Bit 7: onetime_pct
    if is_bit_set(bitvector, 7):
        onetime_pct, offset = decode_uint16(payload, offset)

    # Bit 8: flags (3-bit bitvector)
    if is_bit_set(bitvector, 8):
        flags, offset = read_bitvector(payload, offset, 3)

    # Bit 9: helptext
    if is_bit_set(bitvector, 9):
        helptext, offset = decode_string(payload, offset)

    # Build result dictionary
    result = {
        "id": goods_id,
        "name": name,
        "rule_name": rule_name,
        "reqs_count": reqs_count,
        "reqs": reqs,
        "from_pct": from_pct,
        "to_pct": to_pct,
        "onetime_pct": onetime_pct,
        "flags": flags,
        "helptext": helptext,
    }

    # Update cache for next packet
    delta_cache.update_cache(PACKET_RULESET_GOODS, (), result)

    return result


def decode_ruleset_unit_class_flag(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_UNIT_CLASS_FLAG (230) - unit class flag definition.

    Structure from freeciv-build/packets_gen.c:49592:
    - 3-bit bitvector (1 byte)
    - Bit 0: id (UINT8)
    - Bit 1: name (STRING)
    - Bit 2: helptxt (STRING)
    - Cache: hash_const (all packets share same cache entry)

    Returns:
        Dictionary with decoded fields: id, name, helptxt
    """
    offset = 0

    # Read 3-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 3)

    # Helper to check if field is present
    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (uses empty tuple for hash_const - no key fields)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_UNIT_CLASS_FLAG, ())

    # Initialize from cache or defaults
    if cached:
        flag_id = cached.get("id", 0)
        name = cached.get("name", "")
        helptxt = cached.get("helptxt", "")
    else:
        flag_id = 0
        name = ""
        helptxt = ""

    # Bit 0: id
    if has_field(0):
        flag_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if has_field(1):
        name, offset = decode_string(payload, offset)

    # Bit 2: helptxt
    if has_field(2):
        helptxt, offset = decode_string(payload, offset)

    # Build result
    result = {"id": flag_id, "name": name, "helptxt": helptxt}

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_UNIT_CLASS_FLAG, (), result)

    return result


def decode_ruleset_unit_flag(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_UNIT_FLAG (229) - unit flag definition.

    Structure from freeciv-build/packets_gen.c:49341:
    - 3-bit bitvector (1 byte)
    - Bit 0: id (UINT8)
    - Bit 1: name (STRING)
    - Bit 2: helptxt (STRING)
    - Cache: hash_const (empty tuple key)
    """
    offset = 0

    # Read bitvector
    bitvector, offset = read_bitvector(payload, offset, 3)

    # Get cached packet (hash_const uses empty tuple)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_UNIT_FLAG, ())

    # Initialize from cache or defaults
    if cached:
        flag_id = cached.get("id", 0)
        name = cached.get("name", "")
        helptxt = cached.get("helptxt", "")
    else:
        flag_id = 0
        name = ""
        helptxt = ""

    # Bit 0: id
    if is_bit_set(bitvector, 0):
        flag_id, offset = decode_uint8(payload, offset)

    # Bit 1: name
    if is_bit_set(bitvector, 1):
        name, offset = decode_string(payload, offset)

    # Bit 2: helptxt
    if is_bit_set(bitvector, 2):
        helptxt, offset = decode_string(payload, offset)

    # Build result
    result = {
        "id": flag_id,
        "name": name,
        "helptxt": helptxt,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_UNIT_FLAG, (), result)

    return result


def decode_ruleset_unit_bonus(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_UNIT_BONUS (228) - unit combat bonus configuration.

    Structure from freeciv-build/packets_gen.c:49001-49149:
    - 5-bit bitvector (1 byte)
    - Bit 0: unit (UINT16)
    - Bit 1: flag (UINT8)
    - Bit 2: type (UINT8)
    - Bit 3: value (SINT16, signed)
    - Bit 4: quiet (standalone BOOL - no payload)
    - Cache: hash_key_full (all 5 fields as key)
    """
    offset = 0

    # Read bitvector
    bitvector, offset = read_bitvector(payload, offset, 5)

    # All 5 fields are key fields - need all to form cache key
    # Start with defaults
    unit = 0
    flag = 0
    btype = 0
    value = 0
    quiet = False

    # Bit 0: unit (key field)
    if is_bit_set(bitvector, 0):
        unit, offset = decode_uint16(payload, offset)

    # Bit 1: flag (key field)
    if is_bit_set(bitvector, 1):
        flag, offset = decode_uint8(payload, offset)

    # Bit 2: type (key field)
    if is_bit_set(bitvector, 2):
        btype, offset = decode_uint8(payload, offset)

    # Bit 3: value (key field, signed)
    if is_bit_set(bitvector, 3):
        value, offset = decode_sint16(payload, offset)

    # Bit 4: quiet (standalone BOOL - value in bitvector, no payload)
    quiet = is_bit_set(bitvector, 4)

    # Build cache key from all 5 fields
    cache_key = (unit, flag, btype, value, quiet)

    # Get cached packet
    cached = delta_cache.get_cached_packet(PACKET_RULESET_UNIT_BONUS, cache_key)

    # If cached, use cached values for fields not in bitvector
    if cached:
        if not is_bit_set(bitvector, 0):
            unit = cached.get("unit", 0)
        if not is_bit_set(bitvector, 1):
            flag = cached.get("flag", 0)
        if not is_bit_set(bitvector, 2):
            btype = cached.get("type", 0)
        if not is_bit_set(bitvector, 3):
            value = cached.get("value", 0)
        if not is_bit_set(bitvector, 4):
            quiet = cached.get("quiet", False)

    # Build result
    result = {"unit": unit, "flag": flag, "type": btype, "value": value, "quiet": quiet}

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_UNIT_BONUS, cache_key, result)

    return result


def decode_ruleset_tech(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_TECH (144) - technology definition.

    Structure from freeciv-build/packets_gen.c:52170:
    - 2-byte bitvector (14 bits)
    - 14 conditional fields
    - Cache: hash_const (all packets share same cache entry)
    """
    offset = 0

    # Read 14-bit bitvector (2 bytes)
    bitvector, offset = read_bitvector(payload, offset, 14)
    # DEBUG
    # print(f"[DEBUG] TECH bitvector: 0x{bitvector:04x}, bits: {[i for i in range(14) if is_bit_set(bitvector, i)]}")

    def has_field(bit_index: int) -> bool:
        return is_bit_set(bitvector, bit_index)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_TECH, ())

    # Initialize from cache or defaults
    if cached:
        tech_id = cached.get("id", 0)
        root_req = cached.get("root_req", 0)
        research_reqs_count = cached.get("research_reqs_count", 0)
        research_reqs = cached.get("research_reqs", []).copy()
        tclass = cached.get("tclass", 0)
        removed = cached.get("removed", False)
        flags = cached.get("flags", 0)
        cost = cached.get("cost", 0.0)
        num_reqs = cached.get("num_reqs", 0)
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        helptext = cached.get("helptext", "")
        graphic_str = cached.get("graphic_str", "")
        graphic_alt = cached.get("graphic_alt", "")
    else:
        tech_id = 0
        root_req = 0
        research_reqs_count = 0
        research_reqs = []
        tclass = 0
        removed = False
        flags = 0
        cost = 0.0
        num_reqs = 0
        name = ""
        rule_name = ""
        helptext = ""
        graphic_str = ""
        graphic_alt = ""

    # Bit 0: id (UINT16)
    if has_field(0):
        tech_id, offset = decode_uint16(payload, offset)

    # Bit 1: root_req (UINT16)
    if has_field(1):
        root_req, offset = decode_uint16(payload, offset)

    # Bit 2: research_reqs_count (UINT8)
    if has_field(2):
        research_reqs_count, offset = decode_uint8(payload, offset)

    # Bit 3: research_reqs (REQUIREMENT array)
    if has_field(3):
        research_reqs = []
        for _ in range(research_reqs_count):
            req, offset = decode_requirement(payload, offset)
            research_reqs.append(req)

    # Bit 4: tclass (UINT8)
    if has_field(4):
        tclass, offset = decode_uint8(payload, offset)

    # Bit 5: removed (BOOL) - Header folded! Bit IS value, no payload byte
    removed = has_field(5)

    # Bit 6: flags (BV_TECH_FLAGS - 2 bytes for 13 flags)
    if has_field(6):
        flags, offset = read_bitvector(payload, offset, 16)

    # Bit 7: cost (UFLOAT10x3 with factor 100)
    if has_field(7):
        cost, offset = decode_ufloat(payload, offset, 100)

    # Bit 8: num_reqs (UINT32)
    if has_field(8):
        num_reqs, offset = decode_uint32(payload, offset)

    # Bit 9: name (STRING)
    if has_field(9):
        name, offset = decode_string(payload, offset)

    # Bit 10: rule_name (STRING)
    if has_field(10):
        rule_name, offset = decode_string(payload, offset)

    # Bit 11: helptext (STRING)
    if has_field(11):
        helptext, offset = decode_string(payload, offset)

    # Bit 12: graphic_str (STRING)
    if has_field(12):
        graphic_str, offset = decode_string(payload, offset)

    # Bit 13: graphic_alt (STRING)
    if has_field(13):
        graphic_alt, offset = decode_string(payload, offset)

    # Build result
    result = {
        "id": tech_id,
        "root_req": root_req,
        "research_reqs_count": research_reqs_count,
        "research_reqs": research_reqs,
        "tclass": tclass,
        "removed": removed,
        "flags": flags,
        "cost": cost,
        "num_reqs": num_reqs,
        "name": name,
        "rule_name": rule_name,
        "helptext": helptext,
        "graphic_str": graphic_str,
        "graphic_alt": graphic_alt,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_TECH, (), result)

    return result


def decode_ruleset_government_ruler_title(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_GOVERNMENT_RULER_TITLE (143).

    Ruler titles define the male/female titles for government/nation combinations.
    Multiple packets sent (one per government/nation pair) during initialization.

    Delta protocol with empty tuple cache key (hash_const).
    Reference: freeciv-build/packets_gen.c:51860

    Wire format:
    - Byte 0: bitvector (4 bits used for 4 fields)
    - Conditional fields based on bitvector:
      - Bit 0 set: SINT8 gov (government type ID)
      - Bit 1 set: SINT16 nation (nation type ID)
      - Bit 2 set: STRING male_title
      - Bit 3 set: STRING female_title
    """
    offset = 0

    # Read 4-bit bitvector (1 byte)
    bitvector, offset = read_bitvector(payload, offset, 4)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_GOVERNMENT_RULER_TITLE, ())

    # Initialize from cache or defaults
    if cached:
        gov = cached.get("gov", 0)
        nation = cached.get("nation", 0)
        male_title = cached.get("male_title", "")
        female_title = cached.get("female_title", "")
    else:
        gov = 0
        nation = 0
        male_title = ""
        female_title = ""

    # Decode conditional fields based on bitvector
    if is_bit_set(bitvector, 0):
        gov, offset = decode_sint8(payload, offset)

    if is_bit_set(bitvector, 1):
        nation, offset = decode_sint16(payload, offset)

    if is_bit_set(bitvector, 2):
        male_title, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 3):
        female_title, offset = decode_string(payload, offset)

    # Build result
    result = {"gov": gov, "nation": nation, "male_title": male_title, "female_title": female_title}

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_GOVERNMENT_RULER_TITLE, (), result)

    return result


def decode_ruleset_government(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_GOVERNMENT (145).

    Delta protocol with empty tuple cache key (hash_const).
    Reference: freeciv-build/packets_gen.c:53476
    """
    offset = 0

    # Read 11-bit bitvector (2 bytes)
    bitvector, offset = read_bitvector(payload, offset, 11)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_GOVERNMENT, ())

    # Initialize from cache or defaults
    if cached:
        gov_id = cached.get("id", 0)
        reqs_count = cached.get("reqs_count", 0)
        reqs = cached.get("reqs", []).copy()
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        graphic_str = cached.get("graphic_str", "")
        graphic_alt = cached.get("graphic_alt", "")
        sound_str = cached.get("sound_str", "")
        sound_alt = cached.get("sound_alt", "")
        sound_alt2 = cached.get("sound_alt2", "")
        helptext = cached.get("helptext", "")
    else:
        gov_id = 0
        reqs_count = 0
        reqs = []
        name = rule_name = graphic_str = graphic_alt = ""
        sound_str = sound_alt = sound_alt2 = helptext = ""

    # Decode conditional fields based on bitvector
    if is_bit_set(bitvector, 0):
        gov_id, offset = decode_sint8(payload, offset)

    if is_bit_set(bitvector, 1):
        reqs_count, offset = decode_uint8(payload, offset)

    if is_bit_set(bitvector, 2):
        reqs = []
        for _ in range(reqs_count):
            req, offset = decode_requirement(payload, offset)
            reqs.append(req)

    if is_bit_set(bitvector, 3):
        name, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 4):
        rule_name, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 5):
        graphic_str, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 6):
        graphic_alt, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 7):
        sound_str, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 8):
        sound_alt, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 9):
        sound_alt2, offset = decode_string(payload, offset)

    if is_bit_set(bitvector, 10):
        helptext, offset = decode_string(payload, offset)

    # Build result
    result = {
        "id": gov_id,
        "reqs_count": reqs_count,
        "reqs": reqs,
        "name": name,
        "rule_name": rule_name,
        "graphic_str": graphic_str,
        "graphic_alt": graphic_alt,
        "sound_str": sound_str,
        "sound_alt": sound_alt,
        "sound_alt2": sound_alt2,
        "helptext": helptext,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_GOVERNMENT, (), result)

    return result


def decode_ruleset_unit(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_UNIT (140) - unit type definition.

    Delta protocol with empty tuple cache key (hash_const).
    Reference: freeciv-build/packets_gen.c:46262-47400

    48-bit bitvector, 47 conditional fields.
    Bit 47 (worker) uses boolean header folding - NO payload bytes consumed.
    Nested bitvectors for cargo, targets, embarks, disembarks, flags, roles.
    """
    offset = 0

    # Read 48-bit bitvector (6 bytes)
    bitvector, offset = read_bitvector(payload, offset, 48)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_UNIT, ())

    # Initialize from cache or defaults
    if cached:
        unit_id = cached.get("id", 0)
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        graphic_str = cached.get("graphic_str", "")
        graphic_alt = cached.get("graphic_alt", "")
        graphic_alt2 = cached.get("graphic_alt2", "")
        sound_move = cached.get("sound_move", "")
        sound_move_alt = cached.get("sound_move_alt", "")
        sound_fight = cached.get("sound_fight", "")
        sound_fight_alt = cached.get("sound_fight_alt", "")
        unit_class_id = cached.get("unit_class_id", 0)
        build_cost = cached.get("build_cost", 0)
        pop_cost = cached.get("pop_cost", 0)
        attack_strength = cached.get("attack_strength", 0)
        defense_strength = cached.get("defense_strength", 0)
        move_rate = cached.get("move_rate", 0)
        build_reqs_count = cached.get("build_reqs_count", 0)
        build_reqs = cached.get("build_reqs", []).copy()
        vision_radius_sq = cached.get("vision_radius_sq", 0)
        transport_capacity = cached.get("transport_capacity", 0)
        hp = cached.get("hp", 0)
        firepower = cached.get("firepower", 0)
        obsoleted_by = cached.get("obsoleted_by", 0)
        converted_to = cached.get("converted_to", 0)
        convert_time = cached.get("convert_time", 0)
        fuel = cached.get("fuel", 0)
        happy_cost = cached.get("happy_cost", 0)
        upkeep = cached.get("upkeep", [0] * O_LAST).copy()
        paratroopers_range = cached.get("paratroopers_range", 0)
        veteran_levels = cached.get("veteran_levels", 0)
        veteran_name = cached.get("veteran_name", []).copy()
        power_fact = cached.get("power_fact", []).copy()
        move_bonus = cached.get("move_bonus", []).copy()
        base_raise_chance = cached.get("base_raise_chance", []).copy()
        work_raise_chance = cached.get("work_raise_chance", []).copy()
        bombard_rate = cached.get("bombard_rate", 0)
        city_size = cached.get("city_size", 0)
        city_slots = cached.get("city_slots", 0)
        tp_defense = cached.get("tp_defense", 0)
        cargo = cached.get("cargo", 0)
        targets = cached.get("targets", 0)
        embarks = cached.get("embarks", 0)
        disembarks = cached.get("disembarks", 0)
        vlayer = cached.get("vlayer", 0)
        helptext = cached.get("helptext", "")
        flags = cached.get("flags", 0)
        roles = cached.get("roles", 0)
        worker = cached.get("worker", False)
    else:
        unit_id = 0
        name = rule_name = graphic_str = graphic_alt = graphic_alt2 = ""
        sound_move = sound_move_alt = sound_fight = sound_fight_alt = ""
        unit_class_id = build_cost = pop_cost = 0
        attack_strength = defense_strength = move_rate = 0
        build_reqs_count = 0
        build_reqs = []
        vision_radius_sq = transport_capacity = hp = firepower = 0
        obsoleted_by = converted_to = convert_time = fuel = happy_cost = 0
        upkeep = [0] * O_LAST
        paratroopers_range = veteran_levels = 0
        veteran_name = []
        power_fact = []
        move_bonus = []
        base_raise_chance = []
        work_raise_chance = []
        bombard_rate = city_size = city_slots = tp_defense = 0
        cargo = targets = embarks = disembarks = 0
        vlayer = 0
        helptext = ""
        flags = roles = 0
        worker = False

    # Decode conditional fields based on bitvector
    # Bit 0: id (UINT16)
    if is_bit_set(bitvector, 0):
        unit_id, offset = decode_uint16(payload, offset)

    # Bit 1: name (STRING)
    if is_bit_set(bitvector, 1):
        name, offset = decode_string(payload, offset)

    # Bit 2: rule_name (STRING)
    if is_bit_set(bitvector, 2):
        rule_name, offset = decode_string(payload, offset)

    # Bit 3: graphic_str (STRING)
    if is_bit_set(bitvector, 3):
        graphic_str, offset = decode_string(payload, offset)

    # Bit 4: graphic_alt (STRING)
    if is_bit_set(bitvector, 4):
        graphic_alt, offset = decode_string(payload, offset)

    # Bit 5: graphic_alt2 (STRING)
    if is_bit_set(bitvector, 5):
        graphic_alt2, offset = decode_string(payload, offset)

    # Bit 6: sound_move (STRING)
    if is_bit_set(bitvector, 6):
        sound_move, offset = decode_string(payload, offset)

    # Bit 7: sound_move_alt (STRING)
    if is_bit_set(bitvector, 7):
        sound_move_alt, offset = decode_string(payload, offset)

    # Bit 8: sound_fight (STRING)
    if is_bit_set(bitvector, 8):
        sound_fight, offset = decode_string(payload, offset)

    # Bit 9: sound_fight_alt (STRING)
    if is_bit_set(bitvector, 9):
        sound_fight_alt, offset = decode_string(payload, offset)

    # Bit 10: unit_class_id (UINT8)
    if is_bit_set(bitvector, 10):
        unit_class_id, offset = decode_uint8(payload, offset)

    # Bit 11: build_cost (UINT16)
    if is_bit_set(bitvector, 11):
        build_cost, offset = decode_uint16(payload, offset)

    # Bit 12: pop_cost (UINT8)
    if is_bit_set(bitvector, 12):
        pop_cost, offset = decode_uint8(payload, offset)

    # Bit 13: attack_strength (UINT8)
    if is_bit_set(bitvector, 13):
        attack_strength, offset = decode_uint8(payload, offset)

    # Bit 14: defense_strength (UINT8)
    if is_bit_set(bitvector, 14):
        defense_strength, offset = decode_uint8(payload, offset)

    # Bit 15: move_rate (UINT32)
    if is_bit_set(bitvector, 15):
        move_rate, offset = decode_uint32(payload, offset)

    # Bit 16: build_reqs_count (UINT8)
    if is_bit_set(bitvector, 16):
        build_reqs_count, offset = decode_uint8(payload, offset)

    # Bit 17: build_reqs array (REQUIREMENT[build_reqs_count])
    if is_bit_set(bitvector, 17):
        build_reqs = []
        for _ in range(build_reqs_count):
            req, offset = decode_requirement(payload, offset)
            build_reqs.append(req)

    # Bit 18: vision_radius_sq (UINT16)
    if is_bit_set(bitvector, 18):
        vision_radius_sq, offset = decode_uint16(payload, offset)

    # Bit 19: transport_capacity (UINT8)
    if is_bit_set(bitvector, 19):
        transport_capacity, offset = decode_uint8(payload, offset)

    # Bit 20: hp (UINT8)
    if is_bit_set(bitvector, 20):
        hp, offset = decode_uint8(payload, offset)

    # Bit 21: firepower (UINT8)
    if is_bit_set(bitvector, 21):
        firepower, offset = decode_uint8(payload, offset)

    # Bit 22: obsoleted_by (UINT8)
    if is_bit_set(bitvector, 22):
        obsoleted_by, offset = decode_uint8(payload, offset)

    # Bit 23: converted_to (UINT8)
    if is_bit_set(bitvector, 23):
        converted_to, offset = decode_uint8(payload, offset)

    # Bit 24: convert_time (UINT8)
    if is_bit_set(bitvector, 24):
        convert_time, offset = decode_uint8(payload, offset)

    # Bit 25: fuel (UINT8)
    if is_bit_set(bitvector, 25):
        fuel, offset = decode_uint8(payload, offset)

    # Bit 26: happy_cost (UINT8)
    if is_bit_set(bitvector, 26):
        happy_cost, offset = decode_uint8(payload, offset)

    # Bit 27: upkeep[O_LAST] (UINT8 array, fixed 6 elements)
    if is_bit_set(bitvector, 27):
        upkeep = []
        for _ in range(O_LAST):
            val, offset = decode_uint8(payload, offset)
            upkeep.append(val)

    # Bit 28: paratroopers_range (UINT16)
    if is_bit_set(bitvector, 28):
        paratroopers_range, offset = decode_uint16(payload, offset)

    # Bit 29: veteran_levels (UINT8) - needed for sizing arrays
    if is_bit_set(bitvector, 29):
        veteran_levels, offset = decode_uint8(payload, offset)

    # Bit 30: veteran_name[veteran_levels] (STRING array)
    if is_bit_set(bitvector, 30):
        veteran_name = []
        for _ in range(veteran_levels):
            vname, offset = decode_string(payload, offset)
            veteran_name.append(vname)

    # Bit 31: power_fact[veteran_levels] (UINT16 array)
    if is_bit_set(bitvector, 31):
        power_fact = []
        for _ in range(veteran_levels):
            val, offset = decode_uint16(payload, offset)
            power_fact.append(val)

    # Bit 32: move_bonus[veteran_levels] (UINT32 array)
    if is_bit_set(bitvector, 32):
        move_bonus = []
        for _ in range(veteran_levels):
            val, offset = decode_uint32(payload, offset)
            move_bonus.append(val)

    # Bit 33: base_raise_chance[veteran_levels] (UINT8 array)
    if is_bit_set(bitvector, 33):
        base_raise_chance = []
        for _ in range(veteran_levels):
            val, offset = decode_uint8(payload, offset)
            base_raise_chance.append(val)

    # Bit 34: work_raise_chance[veteran_levels] (UINT8 array)
    if is_bit_set(bitvector, 34):
        work_raise_chance = []
        for _ in range(veteran_levels):
            val, offset = decode_uint8(payload, offset)
            work_raise_chance.append(val)

    # Bit 35: bombard_rate (UINT8)
    if is_bit_set(bitvector, 35):
        bombard_rate, offset = decode_uint8(payload, offset)

    # Bit 36: city_size (UINT8)
    if is_bit_set(bitvector, 36):
        city_size, offset = decode_uint8(payload, offset)

    # Bit 37: city_slots (UINT8)
    if is_bit_set(bitvector, 37):
        city_slots, offset = decode_uint8(payload, offset)

    # Bit 38: tp_defense (UINT8 enum)
    if is_bit_set(bitvector, 38):
        tp_defense, offset = decode_uint8(payload, offset)

    # Bit 39: cargo (BV_UNIT_CLASSES bitvector - 32 bits = 4 bytes)
    if is_bit_set(bitvector, 39):
        cargo, offset = read_bitvector(payload, offset, 32)

    # Bit 40: targets (BV_UNIT_CLASSES bitvector - 32 bits = 4 bytes)
    if is_bit_set(bitvector, 40):
        targets, offset = read_bitvector(payload, offset, 32)

    # Bit 41: embarks (BV_UNIT_CLASSES bitvector - 32 bits = 4 bytes)
    if is_bit_set(bitvector, 41):
        embarks, offset = read_bitvector(payload, offset, 32)

    # Bit 42: disembarks (BV_UNIT_CLASSES bitvector - 32 bits = 4 bytes)
    if is_bit_set(bitvector, 42):
        disembarks, offset = read_bitvector(payload, offset, 32)

    # Bit 43: vlayer (UINT8 enum)
    if is_bit_set(bitvector, 43):
        vlayer, offset = decode_uint8(payload, offset)

    # Bit 44: helptext (STRING)
    if is_bit_set(bitvector, 44):
        helptext, offset = decode_string(payload, offset)

    # Bit 45: flags (BV_UTYPE_FLAGS bitvector - estimated 128 bits = 16 bytes)
    # TODO: Verify size with captured packets
    if is_bit_set(bitvector, 45):
        flags, offset = read_bitvector(payload, offset, 128)

    # Bit 46: roles (BV_UTYPE_ROLES bitvector - L_MAX = 64 bits = 8 bytes)
    if is_bit_set(bitvector, 46):
        roles, offset = read_bitvector(payload, offset, 64)

    # Bit 47: worker (BOOL - boolean header folding, NO payload bytes)
    worker = is_bit_set(bitvector, 47)

    # Build result dictionary
    result = {
        "id": unit_id,
        "name": name,
        "rule_name": rule_name,
        "graphic_str": graphic_str,
        "graphic_alt": graphic_alt,
        "graphic_alt2": graphic_alt2,
        "sound_move": sound_move,
        "sound_move_alt": sound_move_alt,
        "sound_fight": sound_fight,
        "sound_fight_alt": sound_fight_alt,
        "unit_class_id": unit_class_id,
        "build_cost": build_cost,
        "pop_cost": pop_cost,
        "attack_strength": attack_strength,
        "defense_strength": defense_strength,
        "move_rate": move_rate,
        "build_reqs_count": build_reqs_count,
        "build_reqs": build_reqs,
        "vision_radius_sq": vision_radius_sq,
        "transport_capacity": transport_capacity,
        "hp": hp,
        "firepower": firepower,
        "obsoleted_by": obsoleted_by,
        "converted_to": converted_to,
        "convert_time": convert_time,
        "fuel": fuel,
        "happy_cost": happy_cost,
        "upkeep": upkeep,
        "paratroopers_range": paratroopers_range,
        "veteran_levels": veteran_levels,
        "veteran_name": veteran_name,
        "power_fact": power_fact,
        "move_bonus": move_bonus,
        "base_raise_chance": base_raise_chance,
        "work_raise_chance": work_raise_chance,
        "bombard_rate": bombard_rate,
        "city_size": city_size,
        "city_slots": city_slots,
        "tp_defense": tp_defense,
        "cargo": cargo,
        "targets": targets,
        "embarks": embarks,
        "disembarks": disembarks,
        "vlayer": vlayer,
        "helptext": helptext,
        "flags": flags,
        "roles": roles,
        "worker": worker,
    }

    # Update cache
    delta_cache.update_cache(PACKET_RULESET_UNIT, (), result)

    return result


def decode_ruleset_extra(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_EXTRA (232) - extra type definition.

    Extras are terrain features like forests, rivers, roads, bases, and other
    map improvements. This packet defines properties and behavior of each extra.

    Delta protocol with empty tuple cache key (hash_const).
    Reference: freeciv-build/packets_gen.c:63020-63900

    6-byte bitvector (41 conditional fields).
    Bits 25-26 (buildable, generated) use boolean header folding - NO payload bytes.
    Nested bitvectors: causes (16 bits), rmcauses (8 bits), native_to (32 bits),
    flags (22 bits), hidden_by/bridged_over/conflicts (250 bits each).
    """
    offset = 0

    # Read 6-byte bitvector (41 bits)
    bitvector, offset = read_bitvector(payload, offset, 41)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_EXTRA, ())

    # Initialize from cache or defaults
    if cached:
        extra_id = cached.get("id", 0)
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        category = cached.get("category", 0)
        causes = cached.get("causes", 0)
        rmcauses = cached.get("rmcauses", 0)
        activity_gfx = cached.get("activity_gfx", "")
        act_gfx_alt = cached.get("act_gfx_alt", "")
        act_gfx_alt2 = cached.get("act_gfx_alt2", "")
        rmact_gfx = cached.get("rmact_gfx", "")
        rmact_gfx_alt = cached.get("rmact_gfx_alt", "")
        rmact_gfx_alt2 = cached.get("rmact_gfx_alt2", "")
        graphic_str = cached.get("graphic_str", "")
        graphic_alt = cached.get("graphic_alt", "")
        reqs_count = cached.get("reqs_count", 0)
        reqs = cached.get("reqs", []).copy()
        rmreqs_count = cached.get("rmreqs_count", 0)
        rmreqs = cached.get("rmreqs", []).copy()
        appearance_chance = cached.get("appearance_chance", 0)
        appearance_reqs_count = cached.get("appearance_reqs_count", 0)
        appearance_reqs = cached.get("appearance_reqs", []).copy()
        disappearance_chance = cached.get("disappearance_chance", 0)
        disappearance_reqs_count = cached.get("disappearance_reqs_count", 0)
        disappearance_reqs = cached.get("disappearance_reqs", []).copy()
        visibility_req = cached.get("visibility_req", 0)
        buildable = cached.get("buildable", False)
        generated = cached.get("generated", False)
        build_time = cached.get("build_time", 0)
        build_time_factor = cached.get("build_time_factor", 0)
        removal_time = cached.get("removal_time", 0)
        removal_time_factor = cached.get("removal_time_factor", 0)
        infracost = cached.get("infracost", 0)
        defense_bonus = cached.get("defense_bonus", 0)
        eus = cached.get("eus", 0)
        native_to = cached.get("native_to", 0)
        flags = cached.get("flags", 0)
        hidden_by = cached.get("hidden_by", 0)
        bridged_over = cached.get("bridged_over", 0)
        conflicts = cached.get("conflicts", 0)
        no_aggr_near_city = cached.get("no_aggr_near_city", 0)
        helptext = cached.get("helptext", "")
    else:
        extra_id = 0
        name = rule_name = ""
        category = 0
        causes = rmcauses = 0
        activity_gfx = act_gfx_alt = act_gfx_alt2 = ""
        rmact_gfx = rmact_gfx_alt = rmact_gfx_alt2 = ""
        graphic_str = graphic_alt = ""
        reqs_count = 0
        reqs = []
        rmreqs_count = 0
        rmreqs = []
        appearance_chance = 0
        appearance_reqs_count = 0
        appearance_reqs = []
        disappearance_chance = 0
        disappearance_reqs_count = 0
        disappearance_reqs = []
        visibility_req = 0
        buildable = generated = False
        build_time = build_time_factor = 0
        removal_time = removal_time_factor = 0
        infracost = defense_bonus = eus = 0
        native_to = flags = 0
        hidden_by = bridged_over = conflicts = 0
        no_aggr_near_city = 0
        helptext = ""

    # Decode conditional fields based on bitvector
    # Bit 0: id (UINT8)
    if is_bit_set(bitvector, 0):
        extra_id, offset = decode_uint8(payload, offset)

    # Bit 1: name (STRING)
    if is_bit_set(bitvector, 1):
        name, offset = decode_string(payload, offset)

    # Bit 2: rule_name (STRING)
    if is_bit_set(bitvector, 2):
        rule_name, offset = decode_string(payload, offset)

    # Bit 3: category (UINT8)
    if is_bit_set(bitvector, 3):
        category, offset = decode_uint8(payload, offset)

    # Bit 4: causes (nested bitvector, 16 bits = 2 bytes)
    if is_bit_set(bitvector, 4):
        causes, offset = read_bitvector(payload, offset, 16)

    # Bit 5: rmcauses (nested bitvector, 8 bits = 1 byte)
    if is_bit_set(bitvector, 5):
        rmcauses, offset = read_bitvector(payload, offset, 8)

    # Bit 6: activity_gfx (STRING)
    if is_bit_set(bitvector, 6):
        activity_gfx, offset = decode_string(payload, offset)

    # Bit 7: act_gfx_alt (STRING)
    if is_bit_set(bitvector, 7):
        act_gfx_alt, offset = decode_string(payload, offset)

    # Bit 8: act_gfx_alt2 (STRING)
    if is_bit_set(bitvector, 8):
        act_gfx_alt2, offset = decode_string(payload, offset)

    # Bit 9: rmact_gfx (STRING)
    if is_bit_set(bitvector, 9):
        rmact_gfx, offset = decode_string(payload, offset)

    # Bit 10: rmact_gfx_alt (STRING)
    if is_bit_set(bitvector, 10):
        rmact_gfx_alt, offset = decode_string(payload, offset)

    # Bit 11: rmact_gfx_alt2 (STRING)
    if is_bit_set(bitvector, 11):
        rmact_gfx_alt2, offset = decode_string(payload, offset)

    # Bit 12: graphic_str (STRING)
    if is_bit_set(bitvector, 12):
        graphic_str, offset = decode_string(payload, offset)

    # Bit 13: graphic_alt (STRING)
    if is_bit_set(bitvector, 13):
        graphic_alt, offset = decode_string(payload, offset)

    # Bit 14: reqs_count (UINT8)
    if is_bit_set(bitvector, 14):
        reqs_count, offset = decode_uint8(payload, offset)

    # Bit 15: reqs (REQUIREMENT array)
    if is_bit_set(bitvector, 15):
        reqs = []
        for _ in range(reqs_count):
            req, offset = decode_requirement(payload, offset)
            reqs.append(req)

    # Bit 16: rmreqs_count (UINT8)
    if is_bit_set(bitvector, 16):
        rmreqs_count, offset = decode_uint8(payload, offset)

    # Bit 17: rmreqs (REQUIREMENT array)
    if is_bit_set(bitvector, 17):
        rmreqs = []
        for _ in range(rmreqs_count):
            req, offset = decode_requirement(payload, offset)
            rmreqs.append(req)

    # Bit 18: appearance_chance (UINT16)
    if is_bit_set(bitvector, 18):
        appearance_chance, offset = decode_uint16(payload, offset)

    # Bit 19: appearance_reqs_count (UINT8)
    if is_bit_set(bitvector, 19):
        appearance_reqs_count, offset = decode_uint8(payload, offset)

    # Bit 20: appearance_reqs (REQUIREMENT array)
    if is_bit_set(bitvector, 20):
        appearance_reqs = []
        for _ in range(appearance_reqs_count):
            req, offset = decode_requirement(payload, offset)
            appearance_reqs.append(req)

    # Bit 21: disappearance_chance (UINT16)
    if is_bit_set(bitvector, 21):
        disappearance_chance, offset = decode_uint16(payload, offset)

    # Bit 22: disappearance_reqs_count (UINT8)
    if is_bit_set(bitvector, 22):
        disappearance_reqs_count, offset = decode_uint8(payload, offset)

    # Bit 23: disappearance_reqs (REQUIREMENT array)
    if is_bit_set(bitvector, 23):
        disappearance_reqs = []
        for _ in range(disappearance_reqs_count):
            req, offset = decode_requirement(payload, offset)
            disappearance_reqs.append(req)

    # Bit 24: visibility_req (UINT16)
    if is_bit_set(bitvector, 24):
        visibility_req, offset = decode_uint16(payload, offset)

    # Bit 25: buildable (BOOLEAN HEADER FOLDING - NO payload bytes!)
    buildable = is_bit_set(bitvector, 25)

    # Bit 26: generated (BOOLEAN HEADER FOLDING - NO payload bytes!)
    generated = is_bit_set(bitvector, 26)

    # Bit 27: build_time (UINT8)
    if is_bit_set(bitvector, 27):
        build_time, offset = decode_uint8(payload, offset)

    # Bit 28: build_time_factor (UINT8)
    if is_bit_set(bitvector, 28):
        build_time_factor, offset = decode_uint8(payload, offset)

    # Bit 29: removal_time (UINT8)
    if is_bit_set(bitvector, 29):
        removal_time, offset = decode_uint8(payload, offset)

    # Bit 30: removal_time_factor (UINT8)
    if is_bit_set(bitvector, 30):
        removal_time_factor, offset = decode_uint8(payload, offset)

    # Bit 31: infracost (UINT16)
    if is_bit_set(bitvector, 31):
        infracost, offset = decode_uint16(payload, offset)

    # Bit 32: defense_bonus (UINT8)
    if is_bit_set(bitvector, 32):
        defense_bonus, offset = decode_uint8(payload, offset)

    # Bit 33: eus (UINT8 - extra_unit_seen_type enum)
    if is_bit_set(bitvector, 33):
        eus, offset = decode_uint8(payload, offset)

    # Bit 34: native_to (nested bitvector, 32 bits = 4 bytes)
    if is_bit_set(bitvector, 34):
        native_to, offset = read_bitvector(payload, offset, 32)

    # Bit 35: flags (nested bitvector, 22 bits = 3 bytes)
    if is_bit_set(bitvector, 35):
        flags, offset = read_bitvector(payload, offset, 22)

    # Bit 36: hidden_by (nested bitvector, 250 bits = 32 bytes)
    if is_bit_set(bitvector, 36):
        hidden_by, offset = read_bitvector(payload, offset, 250)

    # Bit 37: bridged_over (nested bitvector, 250 bits = 32 bytes)
    if is_bit_set(bitvector, 37):
        bridged_over, offset = read_bitvector(payload, offset, 250)

    # Bit 38: conflicts (nested bitvector, 250 bits = 32 bytes)
    if is_bit_set(bitvector, 38):
        conflicts, offset = read_bitvector(payload, offset, 250)

    # Bit 39: no_aggr_near_city (SINT8)
    if is_bit_set(bitvector, 39):
        no_aggr_near_city, offset = decode_sint8(payload, offset)

    # Bit 40: helptext (STRING)
    if is_bit_set(bitvector, 40):
        helptext, offset = decode_string(payload, offset)

    # Build result dict with all 41 fields
    result = {
        "id": extra_id,
        "name": name,
        "rule_name": rule_name,
        "category": category,
        "causes": causes,
        "rmcauses": rmcauses,
        "activity_gfx": activity_gfx,
        "act_gfx_alt": act_gfx_alt,
        "act_gfx_alt2": act_gfx_alt2,
        "rmact_gfx": rmact_gfx,
        "rmact_gfx_alt": rmact_gfx_alt,
        "rmact_gfx_alt2": rmact_gfx_alt2,
        "graphic_str": graphic_str,
        "graphic_alt": graphic_alt,
        "reqs_count": reqs_count,
        "reqs": reqs,
        "rmreqs_count": rmreqs_count,
        "rmreqs": rmreqs,
        "appearance_chance": appearance_chance,
        "appearance_reqs_count": appearance_reqs_count,
        "appearance_reqs": appearance_reqs,
        "disappearance_chance": disappearance_chance,
        "disappearance_reqs_count": disappearance_reqs_count,
        "disappearance_reqs": disappearance_reqs,
        "visibility_req": visibility_req,
        "buildable": buildable,
        "generated": generated,
        "build_time": build_time,
        "build_time_factor": build_time_factor,
        "removal_time": removal_time,
        "removal_time_factor": removal_time_factor,
        "infracost": infracost,
        "defense_bonus": defense_bonus,
        "eus": eus,
        "native_to": native_to,
        "flags": flags,
        "hidden_by": hidden_by,
        "bridged_over": bridged_over,
        "conflicts": conflicts,
        "no_aggr_near_city": no_aggr_near_city,
        "helptext": helptext,
    }

    # Update cache with empty tuple key
    delta_cache.update_cache(PACKET_RULESET_EXTRA, (), result)

    return result


def decode_ruleset_terrain_control(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_TERRAIN_CONTROL (146) - terrain control settings.

    Contains global terrain mechanics configuration: movement rules, channel/reclaim
    requirements, lake size limits, and GUI type mappings.

    Delta protocol with empty tuple cache key (no key fields).
    Reference: freeciv-build/packets_gen.c:54153

    2-byte bitvector (12 conditional fields).
    Bits 8-9 (pythagorean_diagonal, infrapoints) use boolean header folding - NO payload bytes.
    """
    offset = 0

    # Read 2-byte bitvector (12 bits)
    bitvector, offset = read_bitvector(payload, offset, 12)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_TERRAIN_CONTROL, ())

    # Initialize from cache or defaults
    if cached:
        ocean_reclaim_requirement_pct = cached.get("ocean_reclaim_requirement_pct", 0)
        land_channel_requirement_pct = cached.get("land_channel_requirement_pct", 0)
        terrain_thaw_requirement_pct = cached.get("terrain_thaw_requirement_pct", 0)
        terrain_freeze_requirement_pct = cached.get("terrain_freeze_requirement_pct", 0)
        lake_max_size = cached.get("lake_max_size", 0)
        min_start_native_area = cached.get("min_start_native_area", 0)
        move_fragments = cached.get("move_fragments", 0)
        igter_cost = cached.get("igter_cost", 0)
        pythagorean_diagonal = cached.get("pythagorean_diagonal", False)
        infrapoints = cached.get("infrapoints", False)
        gui_type_base0 = cached.get("gui_type_base0", "")
        gui_type_base1 = cached.get("gui_type_base1", "")
    else:
        ocean_reclaim_requirement_pct = 0
        land_channel_requirement_pct = 0
        terrain_thaw_requirement_pct = 0
        terrain_freeze_requirement_pct = 0
        lake_max_size = 0
        min_start_native_area = 0
        move_fragments = 0
        igter_cost = 0
        pythagorean_diagonal = False
        infrapoints = False
        gui_type_base0 = ""
        gui_type_base1 = ""

    # Decode conditional fields based on bitvector
    # Bit 0: ocean_reclaim_requirement_pct (UINT8)
    if is_bit_set(bitvector, 0):
        ocean_reclaim_requirement_pct, offset = decode_uint8(payload, offset)

    # Bit 1: land_channel_requirement_pct (UINT8)
    if is_bit_set(bitvector, 1):
        land_channel_requirement_pct, offset = decode_uint8(payload, offset)

    # Bit 2: terrain_thaw_requirement_pct (UINT8)
    if is_bit_set(bitvector, 2):
        terrain_thaw_requirement_pct, offset = decode_uint8(payload, offset)

    # Bit 3: terrain_freeze_requirement_pct (UINT8)
    if is_bit_set(bitvector, 3):
        terrain_freeze_requirement_pct, offset = decode_uint8(payload, offset)

    # Bit 4: lake_max_size (UINT8)
    if is_bit_set(bitvector, 4):
        lake_max_size, offset = decode_uint8(payload, offset)

    # Bit 5: min_start_native_area (UINT8)
    if is_bit_set(bitvector, 5):
        min_start_native_area, offset = decode_uint8(payload, offset)

    # Bit 6: move_fragments (UINT32)
    if is_bit_set(bitvector, 6):
        move_fragments, offset = decode_uint32(payload, offset)

    # Bit 7: igter_cost (UINT32)
    if is_bit_set(bitvector, 7):
        igter_cost, offset = decode_uint32(payload, offset)

    # Bit 8: pythagorean_diagonal (HEADER-FOLDED - no payload bytes!)
    pythagorean_diagonal = is_bit_set(bitvector, 8)

    # Bit 9: infrapoints (HEADER-FOLDED - no payload bytes!)
    infrapoints = is_bit_set(bitvector, 9)

    # Bit 10: gui_type_base0 (STRING)
    if is_bit_set(bitvector, 10):
        gui_type_base0, offset = decode_string(payload, offset)

    # Bit 11: gui_type_base1 (STRING)
    if is_bit_set(bitvector, 11):
        gui_type_base1, offset = decode_string(payload, offset)

    # Build result dict with all 12 fields
    result = {
        "ocean_reclaim_requirement_pct": ocean_reclaim_requirement_pct,
        "land_channel_requirement_pct": land_channel_requirement_pct,
        "terrain_thaw_requirement_pct": terrain_thaw_requirement_pct,
        "terrain_freeze_requirement_pct": terrain_freeze_requirement_pct,
        "lake_max_size": lake_max_size,
        "min_start_native_area": min_start_native_area,
        "move_fragments": move_fragments,
        "igter_cost": igter_cost,
        "pythagorean_diagonal": pythagorean_diagonal,
        "infrapoints": infrapoints,
        "gui_type_base0": gui_type_base0,
        "gui_type_base1": gui_type_base1,
    }

    # Update cache with empty tuple key
    delta_cache.update_cache(PACKET_RULESET_TERRAIN_CONTROL, (), result)

    return result


def decode_ruleset_building(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_BUILDING (150) - building/improvement type definition.

    Buildings (also called improvements) are structures that can be built in cities,
    including Great Wonders, Small Wonders, and regular improvements (libraries,
    temples, walls, etc.).

    Delta protocol with 'id' as key field.
    Reference: freeciv-build/packets_gen.c:58834

    19 conditional fields (bits 0-18), 3-byte bitvector.
    """
    offset = 0

    # Read 3-byte bitvector (19 conditional fields)
    bitvector, offset = read_bitvector(payload, offset, 19)

    # Get cached packet (keyed by id)
    # Note: We don't have id yet, so we use empty tuple for initial lookup
    cached = delta_cache.get_cached_packet(PACKET_RULESET_BUILDING, ())

    # Initialize from cache or defaults
    if cached:
        building_id = cached.get("id", 0)
        genus = cached.get("genus", 0)
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        graphic_str = cached.get("graphic_str", "")
        graphic_alt = cached.get("graphic_alt", "")
        graphic_alt2 = cached.get("graphic_alt2", "")
        reqs_count = cached.get("reqs_count", 0)
        reqs = cached.get("reqs", []).copy()
        obs_count = cached.get("obs_count", 0)
        obs_reqs = cached.get("obs_reqs", []).copy()
        build_cost = cached.get("build_cost", 0)
        upkeep = cached.get("upkeep", 0)
        sabotage = cached.get("sabotage", 0)
        flags = cached.get("flags", 0)
        soundtag = cached.get("soundtag", "")
        soundtag_alt = cached.get("soundtag_alt", "")
        soundtag_alt2 = cached.get("soundtag_alt2", "")
        helptext = cached.get("helptext", "")
    else:
        building_id = 0
        genus = 0
        name = ""
        rule_name = ""
        graphic_str = ""
        graphic_alt = ""
        graphic_alt2 = ""
        reqs_count = 0
        reqs = []
        obs_count = 0
        obs_reqs = []
        build_cost = 0
        upkeep = 0
        sabotage = 0
        flags = 0
        soundtag = ""
        soundtag_alt = ""
        soundtag_alt2 = ""
        helptext = ""

    # Decode conditional fields based on bitvector
    # Bit 0: id (UINT8) - key field
    if is_bit_set(bitvector, 0):
        building_id, offset = decode_uint8(payload, offset)

    # Bit 1: genus (UINT8)
    if is_bit_set(bitvector, 1):
        genus, offset = decode_uint8(payload, offset)

    # Bit 2: name (STRING)
    if is_bit_set(bitvector, 2):
        name, offset = decode_string(payload, offset)

    # Bit 3: rule_name (STRING)
    if is_bit_set(bitvector, 3):
        rule_name, offset = decode_string(payload, offset)

    # Bit 4: graphic_str (STRING)
    if is_bit_set(bitvector, 4):
        graphic_str, offset = decode_string(payload, offset)

    # Bit 5: graphic_alt (STRING)
    if is_bit_set(bitvector, 5):
        graphic_alt, offset = decode_string(payload, offset)

    # Bit 6: graphic_alt2 (STRING)
    if is_bit_set(bitvector, 6):
        graphic_alt2, offset = decode_string(payload, offset)

    # Bit 7: reqs_count (UINT8)
    if is_bit_set(bitvector, 7):
        reqs_count, offset = decode_uint8(payload, offset)

    # Bit 8: reqs array (REQUIREMENT[], length from reqs_count)
    if is_bit_set(bitvector, 8):
        reqs = []
        for i in range(reqs_count):
            req, offset = decode_requirement(payload, offset)
            reqs.append(req)

    # Bit 9: obs_count (UINT8)
    if is_bit_set(bitvector, 9):
        obs_count, offset = decode_uint8(payload, offset)

    # Bit 10: obs_reqs array (REQUIREMENT[], length from obs_count)
    if is_bit_set(bitvector, 10):
        obs_reqs = []
        for i in range(obs_count):
            req, offset = decode_requirement(payload, offset)
            obs_reqs.append(req)

    # Bit 11: build_cost (UINT16)
    if is_bit_set(bitvector, 11):
        build_cost, offset = decode_uint16(payload, offset)

    # Bit 12: upkeep (UINT8)
    if is_bit_set(bitvector, 12):
        upkeep, offset = decode_uint8(payload, offset)

    # Bit 13: sabotage (UINT8)
    if is_bit_set(bitvector, 13):
        sabotage, offset = decode_uint8(payload, offset)

    # Bit 14: flags (BV_IMPR_FLAGS - bitvector)
    if is_bit_set(bitvector, 14):
        flags, offset = decode_uint16(payload, offset)  # BV_IMPR_FLAGS is 12 bits = 2 bytes

    # Bit 15: soundtag (STRING)
    if is_bit_set(bitvector, 15):
        soundtag, offset = decode_string(payload, offset)

    # Bit 16: soundtag_alt (STRING)
    if is_bit_set(bitvector, 16):
        soundtag_alt, offset = decode_string(payload, offset)

    # Bit 17: soundtag_alt2 (STRING)
    if is_bit_set(bitvector, 17):
        soundtag_alt2, offset = decode_string(payload, offset)

    # Bit 18: helptext (STRING)
    if is_bit_set(bitvector, 18):
        helptext, offset = decode_string(payload, offset)

    # Build result
    result = {
        "id": building_id,
        "genus": genus,
        "name": name,
        "rule_name": rule_name,
        "graphic_str": graphic_str,
        "graphic_alt": graphic_alt,
        "graphic_alt2": graphic_alt2,
        "reqs_count": reqs_count,
        "reqs": reqs,
        "obs_count": obs_count,
        "obs_reqs": obs_reqs,
        "build_cost": build_cost,
        "upkeep": upkeep,
        "sabotage": sabotage,
        "flags": flags,
        "soundtag": soundtag,
        "soundtag_alt": soundtag_alt,
        "soundtag_alt2": soundtag_alt2,
        "helptext": helptext,
    }

    # Update cache with empty tuple (hash_const packet)
    delta_cache.update_cache(PACKET_RULESET_BUILDING, (), result)

    return result


def decode_ruleset_terrain(payload: bytes, delta_cache: "DeltaCache") -> dict:
    """
    Decode PACKET_RULESET_TERRAIN (151) - terrain type definition.

    Contains terrain type data: graphics, movement/combat stats, production output,
    transformations, and visual properties.

    Delta protocol with empty tuple cache key (hash_const).
    Reference: freeciv-build/packets_gen.c:60188

    5-byte bitvector (37 conditional fields, bits 0-36).
    """
    offset = 0

    # Read 5-byte bitvector (37 bits)
    bitvector, offset = read_bitvector(payload, offset, 37)

    # Get cached packet (empty tuple for hash_const)
    cached = delta_cache.get_cached_packet(PACKET_RULESET_TERRAIN, ())

    # Initialize from cache or defaults
    if cached:
        terrain_id = cached.get("id", 0)
        tclass = cached.get("tclass", 0)
        flags = cached.get("flags", 0)
        native_to = cached.get("native_to", 0)
        name = cached.get("name", "")
        rule_name = cached.get("rule_name", "")
        graphic_str = cached.get("graphic_str", "")
        graphic_alt = cached.get("graphic_alt", "")
        graphic_alt2 = cached.get("graphic_alt2", "")
        movement_cost = cached.get("movement_cost", 0)
        defense_bonus = cached.get("defense_bonus", 0)
        output = cached.get("output", [0] * O_LAST)
        num_resources = cached.get("num_resources", 0)
        resources = cached.get("resources", [])
        resource_freq = cached.get("resource_freq", [])
        road_output_incr_pct = cached.get("road_output_incr_pct", [0] * O_LAST)
        base_time = cached.get("base_time", 0)
        road_time = cached.get("road_time", 0)
        cultivate_result = cached.get("cultivate_result", 0)
        cultivate_time = cached.get("cultivate_time", 0)
        plant_result = cached.get("plant_result", 0)
        plant_time = cached.get("plant_time", 0)
        irrigation_food_incr = cached.get("irrigation_food_incr", 0)
        irrigation_time = cached.get("irrigation_time", 0)
        mining_shield_incr = cached.get("mining_shield_incr", 0)
        mining_time = cached.get("mining_time", 0)
        animal = cached.get("animal", 0)
        transform_result = cached.get("transform_result", 0)
        transform_time = cached.get("transform_time", 0)
        placing_time = cached.get("placing_time", 0)
        pillage_time = cached.get("pillage_time", 0)
        extra_count = cached.get("extra_count", 0)
        extra_removal_times = cached.get("extra_removal_times", [])
        color_red = cached.get("color_red", 0)
        color_green = cached.get("color_green", 0)
        color_blue = cached.get("color_blue", 0)
        helptext = cached.get("helptext", "")
    else:
        terrain_id = 0
        tclass = 0
        flags = 0
        native_to = 0
        name = ""
        rule_name = ""
        graphic_str = ""
        graphic_alt = ""
        graphic_alt2 = ""
        movement_cost = 0
        defense_bonus = 0
        output = [0] * O_LAST
        num_resources = 0
        resources = []
        resource_freq = []
        road_output_incr_pct = [0] * O_LAST
        base_time = 0
        road_time = 0
        cultivate_result = 0
        cultivate_time = 0
        plant_result = 0
        plant_time = 0
        irrigation_food_incr = 0
        irrigation_time = 0
        mining_shield_incr = 0
        mining_time = 0
        animal = 0
        transform_result = 0
        transform_time = 0
        placing_time = 0
        pillage_time = 0
        extra_count = 0
        extra_removal_times = []
        color_red = 0
        color_green = 0
        color_blue = 0
        helptext = ""

    # Decode conditional fields based on bitvector

    # Bit 0: id (UINT8)
    if is_bit_set(bitvector, 0):
        terrain_id, offset = decode_uint8(payload, offset)

    # Bit 1: tclass (UINT8)
    if is_bit_set(bitvector, 1):
        tclass, offset = decode_uint8(payload, offset)

    # Bit 2: flags (BV_TERRAIN_FLAGS - 3 bytes for 20 bits)
    if is_bit_set(bitvector, 2):
        flags, offset = read_bitvector(payload, offset, 20)

    # Bit 3: native_to (BV_UNIT_CLASSES - 4 bytes for 32 bits)
    if is_bit_set(bitvector, 3):
        native_to, offset = read_bitvector(payload, offset, 32)

    # Bit 4: name (STRING)
    if is_bit_set(bitvector, 4):
        name, offset = decode_string(payload, offset)

    # Bit 5: rule_name (STRING)
    if is_bit_set(bitvector, 5):
        rule_name, offset = decode_string(payload, offset)

    # Bit 6: graphic_str (STRING)
    if is_bit_set(bitvector, 6):
        graphic_str, offset = decode_string(payload, offset)

    # Bit 7: graphic_alt (STRING)
    if is_bit_set(bitvector, 7):
        graphic_alt, offset = decode_string(payload, offset)

    # Bit 8: graphic_alt2 (STRING)
    if is_bit_set(bitvector, 8):
        graphic_alt2, offset = decode_string(payload, offset)

    # Bit 9: movement_cost (UINT16)
    if is_bit_set(bitvector, 9):
        movement_cost, offset = decode_uint16(payload, offset)

    # Bit 10: defense_bonus (SINT16)
    if is_bit_set(bitvector, 10):
        defense_bonus, offset = decode_sint16(payload, offset)

    # Bit 11: output (array of O_LAST UINT8 values)
    if is_bit_set(bitvector, 11):
        output = []
        for _ in range(O_LAST):
            val, offset = decode_uint8(payload, offset)
            output.append(val)

    # Bit 12: num_resources (UINT8)
    if is_bit_set(bitvector, 12):
        num_resources, offset = decode_uint8(payload, offset)

    # Bit 13: resources (array of UINT8, length num_resources)
    if is_bit_set(bitvector, 13):
        resources = []
        for _ in range(num_resources):
            val, offset = decode_uint8(payload, offset)
            resources.append(val)

    # Bit 14: resource_freq (array of UINT8, length num_resources)
    if is_bit_set(bitvector, 14):
        resource_freq = []
        for _ in range(num_resources):
            val, offset = decode_uint8(payload, offset)
            resource_freq.append(val)

    # Bit 15: road_output_incr_pct (array of O_LAST UINT16 values)
    if is_bit_set(bitvector, 15):
        road_output_incr_pct = []
        for _ in range(O_LAST):
            val, offset = decode_uint16(payload, offset)
            road_output_incr_pct.append(val)

    # Bit 16: base_time (UINT8)
    if is_bit_set(bitvector, 16):
        base_time, offset = decode_uint8(payload, offset)

    # Bit 17: road_time (UINT8)
    if is_bit_set(bitvector, 17):
        road_time, offset = decode_uint8(payload, offset)

    # Bit 18: cultivate_result (UINT8 - Terrain_type_id)
    if is_bit_set(bitvector, 18):
        cultivate_result, offset = decode_uint8(payload, offset)

    # Bit 19: cultivate_time (UINT8)
    if is_bit_set(bitvector, 19):
        cultivate_time, offset = decode_uint8(payload, offset)

    # Bit 20: plant_result (UINT8 - Terrain_type_id)
    if is_bit_set(bitvector, 20):
        plant_result, offset = decode_uint8(payload, offset)

    # Bit 21: plant_time (UINT8)
    if is_bit_set(bitvector, 21):
        plant_time, offset = decode_uint8(payload, offset)

    # Bit 22: irrigation_food_incr (UINT8)
    if is_bit_set(bitvector, 22):
        irrigation_food_incr, offset = decode_uint8(payload, offset)

    # Bit 23: irrigation_time (UINT8)
    if is_bit_set(bitvector, 23):
        irrigation_time, offset = decode_uint8(payload, offset)

    # Bit 24: mining_shield_incr (UINT8)
    if is_bit_set(bitvector, 24):
        mining_shield_incr, offset = decode_uint8(payload, offset)

    # Bit 25: mining_time (UINT8)
    if is_bit_set(bitvector, 25):
        mining_time, offset = decode_uint8(payload, offset)

    # Bit 26: animal (SINT16 - can be -1 for none)
    if is_bit_set(bitvector, 26):
        animal, offset = decode_sint16(payload, offset)

    # Bit 27: transform_result (UINT8 - Terrain_type_id)
    if is_bit_set(bitvector, 27):
        transform_result, offset = decode_uint8(payload, offset)

    # Bit 28: transform_time (UINT8)
    if is_bit_set(bitvector, 28):
        transform_time, offset = decode_uint8(payload, offset)

    # Bit 29: placing_time (UINT8)
    if is_bit_set(bitvector, 29):
        placing_time, offset = decode_uint8(payload, offset)

    # Bit 30: pillage_time (UINT8)
    if is_bit_set(bitvector, 30):
        pillage_time, offset = decode_uint8(payload, offset)

    # Bit 31: extra_count (UINT8)
    if is_bit_set(bitvector, 31):
        extra_count, offset = decode_uint8(payload, offset)

    # Bit 32: extra_removal_times (array of UINT8, length extra_count)
    if is_bit_set(bitvector, 32):
        extra_removal_times = []
        for _ in range(extra_count):
            val, offset = decode_uint8(payload, offset)
            extra_removal_times.append(val)

    # Bit 33: color_red (UINT8)
    if is_bit_set(bitvector, 33):
        color_red, offset = decode_uint8(payload, offset)

    # Bit 34: color_green (UINT8)
    if is_bit_set(bitvector, 34):
        color_green, offset = decode_uint8(payload, offset)

    # Bit 35: color_blue (UINT8)
    if is_bit_set(bitvector, 35):
        color_blue, offset = decode_uint8(payload, offset)

    # Bit 36: helptext (STRING)
    if is_bit_set(bitvector, 36):
        helptext, offset = decode_string(payload, offset)

    # Build result dict with all fields
    result = {
        "id": terrain_id,
        "tclass": tclass,
        "flags": flags,
        "native_to": native_to,
        "name": name,
        "rule_name": rule_name,
        "graphic_str": graphic_str,
        "graphic_alt": graphic_alt,
        "graphic_alt2": graphic_alt2,
        "movement_cost": movement_cost,
        "defense_bonus": defense_bonus,
        "output": output,
        "num_resources": num_resources,
        "resources": resources,
        "resource_freq": resource_freq,
        "road_output_incr_pct": road_output_incr_pct,
        "base_time": base_time,
        "road_time": road_time,
        "cultivate_result": cultivate_result,
        "cultivate_time": cultivate_time,
        "plant_result": plant_result,
        "plant_time": plant_time,
        "irrigation_food_incr": irrigation_food_incr,
        "irrigation_time": irrigation_time,
        "mining_shield_incr": mining_shield_incr,
        "mining_time": mining_time,
        "animal": animal,
        "transform_result": transform_result,
        "transform_time": transform_time,
        "placing_time": placing_time,
        "pillage_time": pillage_time,
        "extra_count": extra_count,
        "extra_removal_times": extra_removal_times,
        "color_red": color_red,
        "color_green": color_green,
        "color_blue": color_blue,
        "helptext": helptext,
    }

    # Update cache with empty tuple key
    delta_cache.update_cache(PACKET_RULESET_TERRAIN, (), result)

    return result


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
    bitvector_bytes = data[offset : offset + num_bytes]
    # Use 'little' because FreeCiv stores bitvectors as byte arrays with LSB-first in each byte
    bitvector = int.from_bytes(bitvector_bytes, "little")
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
    if type_name == "STRING":
        return decode_string(data, offset)
    elif type_name == "SINT32":
        return decode_sint32(data, offset)
    elif type_name == "SINT16":
        return decode_sint16(data, offset)
    elif type_name == "SINT8":
        return decode_sint8(data, offset)
    elif type_name == "UINT32":
        return decode_uint32(data, offset)
    elif type_name == "UINT16":
        return decode_uint16(data, offset)
    elif type_name == "UINT8":
        return decode_uint8(data, offset)
    elif type_name == "BOOL":
        return decode_bool(data, offset)
    else:
        raise ValueError(f"Unsupported field type: {type_name}")


def decode_array_diff(
    data: bytes, offset: int, element_type: str, array_size: int, cached_array: list = None
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
        if element_type == "BOOL":
            result = [False] * array_size
        elif element_type in ("SINT8", "SINT16", "SINT32", "PLAYER"):
            result = [0] * array_size
        elif element_type in ("UINT8", "UINT16", "UINT32"):
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
            raise ValueError(f"Array-diff index {index} exceeds array size {array_size}")

        # Read value for this index
        value, offset = _decode_field(data, offset, element_type)
        result[index] = value

    return result, offset


def decode_delta_packet(payload: bytes, packet_spec: PacketSpec, delta_cache: "DeltaCache") -> dict:
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
        bitvector, offset = read_bitvector(payload, offset, packet_spec.num_bitvector_bits)
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
        cached = {field.name: field.default_value for field in packet_spec.non_key_fields}

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
                    payload, offset, field_spec.element_type, field_spec.array_size, cached_array
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
