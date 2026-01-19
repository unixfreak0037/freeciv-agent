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
    # Encode strings as null-terminated bytes
    username_bytes = username.encode('utf-8') + b'\x00'
    capability_bytes = CAPABILITY.encode('utf-8') + b'\x00'
    version_label_bytes = VERSION_LABEL.encode('utf-8') + b'\x00'

    # Encode version numbers as UINT32 big-endian
    major_bytes = struct.pack('>I', MAJOR_VERSION)
    minor_bytes = struct.pack('>I', MINOR_VERSION)
    patch_bytes = struct.pack('>I', PATCH_VERSION)

    # Build packet payload (without header)
    payload = (username_bytes + capability_bytes + version_label_bytes +
               major_bytes + minor_bytes + patch_bytes)

    # Build complete packet with header
    packet_type = struct.pack('B', PACKET_SERVER_JOIN_REQ)
    packet_length = len(payload) + 3  # 2 bytes length + 1 byte type + payload
    length_header = struct.pack('>H', packet_length)

    return length_header + packet_type + payload


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

    # Parse BOOL you_can_join (1 byte)
    you_can_join = payload[offset] != 0
    offset += 1

    # Helper function to read null-terminated string
    def read_string(data: bytes, start: int) -> Tuple[str, int]:
        end = data.find(b'\x00', start)
        if end == -1:
            raise ValueError("Null terminator not found in string")
        string = data[start:end].decode('utf-8')
        return string, end + 1

    # Parse message
    message, offset = read_string(payload, offset)

    # Parse capability
    capability, offset = read_string(payload, offset)

    # Parse challenge_file
    challenge_file, offset = read_string(payload, offset)

    return {
        'you_can_join': you_can_join,
        'message': message,
        'capability': capability,
        'challenge_file': challenge_file
    }
