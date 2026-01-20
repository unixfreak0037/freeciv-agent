import asyncio
import struct
from typing import Tuple

# Packet type constants
PACKET_PROCESSING_STARTED = 0
PACKET_PROCESSING_FINISHED = 1
PACKET_SERVER_JOIN_REQ = 4
PACKET_SERVER_JOIN_REPLY = 5
PACKET_CHAT_MSG = 25
PACKET_SERVER_INFO = 29
PACKET_GAME_LOAD = 155
PACKET_RULESET_DESCRIPTION_PART = 247
PACKET_RULESET_SUMMARY = 251

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
