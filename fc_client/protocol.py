import socket
import struct
from typing import Tuple

# Packet type constants
PACKET_PROCESSING_STARTED = 0
PACKET_PROCESSING_FINISHED = 1
PACKET_SERVER_JOIN_REQ = 4
PACKET_SERVER_JOIN_REPLY = 5

# Version constants
MAJOR_VERSION = 3
MINOR_VERSION = 3
PATCH_VERSION = 90
VERSION_LABEL = "-dev"
CAPABILITY = "+Freeciv.Devel-3.4-2025.Nov.29"


def _recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Read exactly num_bytes from socket, handling partial reads."""
    data = b''
    while len(data) < num_bytes:
        chunk = sock.recv(num_bytes - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while reading data")
        data += chunk
    return data


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


def read_packet(sock: socket.socket) -> Tuple[int, bytes]:
    """
    Read a packet from the socket.

    Returns:
        Tuple of (packet_type, payload_data)
    """
    # Read 2-byte length field (big-endian)
    length_bytes = _recv_exact(sock, 2)
    packet_length = struct.unpack('>H', length_bytes)[0]

    # Read 1-byte packet type
    type_bytes = _recv_exact(sock, 1)
    packet_type = struct.unpack('B', type_bytes)[0]

    # Read remaining payload (length includes the 2-byte header + 1-byte type)
    payload_length = packet_length - 3
    payload = _recv_exact(sock, payload_length) if payload_length > 0 else b''

    return packet_type, payload


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
