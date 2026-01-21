"""
Unit tests for fc_client/protocol.py

Tests pure functions (encoders, decoders, packet builders) without I/O.
"""

import struct
import pytest

from fc_client import protocol
from fc_client.protocol import (
    # String encoding/decoding
    encode_string,
    decode_string,
    # Boolean encoding/decoding
    encode_bool,
    decode_bool,
    # Integer encoding/decoding
    encode_uint32,
    decode_uint32,
    decode_sint16,
    decode_sint32,
    # Packet encoding
    encode_packet,
    encode_server_join_req,
    # Packet decoding
    decode_server_join_reply,
    decode_server_info,
    decode_chat_msg,
    # Delta protocol helpers
    read_bitvector,
    is_bit_set,
    _decode_field,
    # Constants
    PACKET_SERVER_JOIN_REQ,
    MAJOR_VERSION,
    MINOR_VERSION,
    PATCH_VERSION,
    VERSION_LABEL,
    CAPABILITY,
)


# ============================================================================
# Helper Functions
# ============================================================================


def build_string_bytes(s: str) -> bytes:
    """Helper to build null-terminated string bytes."""
    return s.encode('utf-8') + b'\x00'


def build_uint32_bytes(value: int) -> bytes:
    """Helper to build big-endian UINT32 bytes."""
    return struct.pack('>I', value)


def build_sint16_bytes(value: int) -> bytes:
    """Helper to build big-endian SINT16 bytes."""
    return struct.pack('>h', value)


def build_sint32_bytes(value: int) -> bytes:
    """Helper to build big-endian SINT32 bytes."""
    return struct.pack('>i', value)


# ============================================================================
# Phase 1: Foundation Encoders/Decoders
# ============================================================================


# String encoding/decoding tests (7 tests)


@pytest.mark.unit
def test_encode_string_basic():
    """Test encoding basic ASCII string."""
    result = encode_string("hello")
    assert result == b'hello\x00'


@pytest.mark.unit
def test_encode_string_unicode():
    """Test encoding unicode strings (emoji, Chinese characters)."""
    # Emoji
    result = encode_string("Hello 👋")
    assert result == "Hello 👋".encode('utf-8') + b'\x00'

    # Chinese characters
    result = encode_string("你好")
    assert result == "你好".encode('utf-8') + b'\x00'


@pytest.mark.unit
def test_encode_string_empty():
    """Test encoding empty string returns single null byte."""
    result = encode_string("")
    assert result == b'\x00'


@pytest.mark.unit
def test_decode_string_basic():
    """Test decoding basic null-terminated string."""
    data = b'hello\x00'
    string, new_offset = decode_string(data, 0)
    assert string == "hello"
    assert new_offset == 6  # 5 chars + null terminator


@pytest.mark.unit
def test_decode_string_unicode():
    """Test decoding UTF-8 encoded unicode strings."""
    # Emoji
    data = "Hello 👋".encode('utf-8') + b'\x00'
    string, new_offset = decode_string(data, 0)
    assert string == "Hello 👋"

    # Chinese characters
    data = "你好".encode('utf-8') + b'\x00'
    string, new_offset = decode_string(data, 0)
    assert string == "你好"


@pytest.mark.unit
def test_decode_string_multiple():
    """Test decoding multiple strings in sequence, verify offset tracking."""
    data = b'first\x00second\x00third\x00'

    string1, offset = decode_string(data, 0)
    assert string1 == "first"
    assert offset == 6

    string2, offset = decode_string(data, offset)
    assert string2 == "second"
    assert offset == 13

    string3, offset = decode_string(data, offset)
    assert string3 == "third"
    assert offset == 19


@pytest.mark.unit
def test_decode_string_missing_null():
    """Test error case when null terminator is missing."""
    data = b'hello'  # No null terminator
    with pytest.raises(ValueError, match="Null terminator not found"):
        decode_string(data, 0)


# Boolean encoding/decoding tests (4 tests)


@pytest.mark.unit
def test_encode_bool_true():
    """Test encoding True as byte 0x01."""
    result = encode_bool(True)
    assert result == b'\x01'


@pytest.mark.unit
def test_encode_bool_false():
    """Test encoding False as byte 0x00."""
    result = encode_bool(False)
    assert result == b'\x00'


@pytest.mark.unit
def test_decode_bool_nonzero_is_true():
    """Test that any non-zero byte decodes as True."""
    for value in [1, 5, 127, 255]:
        data = bytes([value])
        result, offset = decode_bool(data, 0)
        assert result is True
        assert offset == 1


@pytest.mark.unit
def test_decode_bool_zero_is_false():
    """Test that zero byte decodes as False."""
    data = b'\x00'
    result, offset = decode_bool(data, 0)
    assert result is False
    assert offset == 1


# Integer encoding/decoding tests (10 tests)


@pytest.mark.unit
def test_encode_uint32_zero():
    """Test encoding UINT32 value 0."""
    result = encode_uint32(0)
    assert result == b'\x00\x00\x00\x00'


@pytest.mark.unit
def test_encode_uint32_max():
    """Test encoding UINT32 max value (2^32-1)."""
    result = encode_uint32(0xFFFFFFFF)
    assert result == b'\xff\xff\xff\xff'


@pytest.mark.unit
def test_encode_uint32_typical():
    """Test encoding typical UINT32 value with big-endian byte order."""
    result = encode_uint32(0x12345678)
    assert result == b'\x12\x34\x56\x78'


@pytest.mark.unit
def test_decode_uint32_various():
    """Test decoding UINT32 values and verify offset advances by 4."""
    # Zero
    data = b'\x00\x00\x00\x00'
    value, offset = decode_uint32(data, 0)
    assert value == 0
    assert offset == 4

    # Max value
    data = b'\xff\xff\xff\xff'
    value, offset = decode_uint32(data, 0)
    assert value == 0xFFFFFFFF
    assert offset == 4

    # Typical value
    data = b'\x12\x34\x56\x78'
    value, offset = decode_uint32(data, 0)
    assert value == 0x12345678
    assert offset == 4


@pytest.mark.unit
def test_decode_sint16_positive():
    """Test decoding positive SINT16 values."""
    data = b'\x00\x2a'  # 42
    value, offset = decode_sint16(data, 0)
    assert value == 42
    assert offset == 2


@pytest.mark.unit
def test_decode_sint16_negative():
    """Test decoding negative SINT16 values."""
    data = b'\xff\xd6'  # -42
    value, offset = decode_sint16(data, 0)
    assert value == -42
    assert offset == 2


@pytest.mark.unit
def test_decode_sint16_boundaries():
    """Test SINT16 boundary values."""
    # Min value: -32768
    data = b'\x80\x00'
    value, offset = decode_sint16(data, 0)
    assert value == -32768
    assert offset == 2

    # Max value: 32767
    data = b'\x7f\xff'
    value, offset = decode_sint16(data, 0)
    assert value == 32767
    assert offset == 2


@pytest.mark.unit
def test_decode_sint32_positive():
    """Test decoding positive SINT32 values."""
    data = b'\x00\x00\x00\x2a'  # 42
    value, offset = decode_sint32(data, 0)
    assert value == 42
    assert offset == 4


@pytest.mark.unit
def test_decode_sint32_negative():
    """Test decoding negative SINT32 values."""
    data = b'\xff\xff\xff\xd6'  # -42
    value, offset = decode_sint32(data, 0)
    assert value == -42
    assert offset == 4


@pytest.mark.unit
def test_decode_sint32_boundaries():
    """Test SINT32 boundary values."""
    # Min value: -2147483648
    data = b'\x80\x00\x00\x00'
    value, offset = decode_sint32(data, 0)
    assert value == -2147483648
    assert offset == 4

    # Max value: 2147483647
    data = b'\x7f\xff\xff\xff'
    value, offset = decode_sint32(data, 0)
    assert value == 2147483647
    assert offset == 4


# ============================================================================
# Phase 2: Packet Infrastructure
# ============================================================================


# Packet encoding tests (5 tests)


@pytest.mark.unit
def test_encode_packet_minimal():
    """Test encoding packet with empty payload, verify header."""
    packet_type = 5
    payload = b''

    result = encode_packet(packet_type, payload)

    # Verify structure: 2-byte length + 1-byte type + payload
    # Total length = 3 (header size) + 0 (payload)
    assert len(result) == 3
    assert result[0:2] == b'\x00\x03'  # Length = 3
    assert result[2] == packet_type  # Type = 5


@pytest.mark.unit
def test_encode_packet_with_payload():
    """Test encoding packet with payload, verify length calculation."""
    packet_type = 25
    payload = b'testdata'

    result = encode_packet(packet_type, payload)

    # Total length = 3 (header) + 8 (payload) = 11
    assert len(result) == 11
    assert result[0:2] == b'\x00\x0b'  # Length = 11
    assert result[2] == packet_type  # Type = 25
    assert result[3:] == payload


@pytest.mark.unit
def test_encode_packet_type_range():
    """Test encoding packet types at boundary (0-255)."""
    # Type 0
    result = encode_packet(0, b'')
    assert result[2] == 0

    # Type 255
    result = encode_packet(255, b'')
    assert result[2] == 255


@pytest.mark.unit
def test_encode_server_join_req():
    """Test encoding complete JOIN_REQ packet."""
    username = "test-user"
    result = encode_server_join_req(username)

    # Verify packet structure
    # First 2 bytes = length (big-endian)
    packet_length = struct.unpack('>H', result[0:2])[0]

    # Third byte = packet type
    packet_type = result[2]
    assert packet_type == PACKET_SERVER_JOIN_REQ

    # Payload should contain: username + capability + version_label + 3x UINT32
    payload = result[3:]
    offset = 0

    # Decode username
    decoded_username, offset = decode_string(payload, offset)
    assert decoded_username == username

    # Decode capability
    decoded_capability, offset = decode_string(payload, offset)
    assert decoded_capability == CAPABILITY

    # Decode version_label
    decoded_version_label, offset = decode_string(payload, offset)
    assert decoded_version_label == VERSION_LABEL


@pytest.mark.unit
def test_encode_server_join_req_constants():
    """Test that JOIN_REQ includes correct version constants."""
    username = "test"
    result = encode_server_join_req(username)

    # Extract payload
    payload = result[3:]

    # Skip strings to get to version integers
    offset = 0
    _, offset = decode_string(payload, offset)  # username
    _, offset = decode_string(payload, offset)  # capability
    _, offset = decode_string(payload, offset)  # version_label

    # Decode version integers
    major, offset = decode_uint32(payload, offset)
    minor, offset = decode_uint32(payload, offset)
    patch, offset = decode_uint32(payload, offset)

    assert major == MAJOR_VERSION
    assert minor == MINOR_VERSION
    assert patch == PATCH_VERSION


# Packet decoding tests (8 tests)


@pytest.mark.unit
def test_decode_server_join_reply_success(sample_join_reply_success):
    """Test decoding successful JOIN_REPLY packet."""
    # Build payload
    payload = (
        encode_bool(True) +
        encode_string("Welcome!") +
        encode_string("+Freeciv-3.0-network") +
        encode_string("")
    )

    result = decode_server_join_reply(payload)

    assert result['you_can_join'] is True
    assert result['message'] == "Welcome!"
    assert result['capability'] == "+Freeciv-3.0-network"
    assert result['challenge_file'] == ""


@pytest.mark.unit
def test_decode_server_join_reply_failure(sample_join_reply_failure):
    """Test decoding failed JOIN_REPLY packet."""
    # Build payload
    payload = (
        encode_bool(False) +
        encode_string("Server full") +
        encode_string("+Freeciv-3.0-network") +
        encode_string("")
    )

    result = decode_server_join_reply(payload)

    assert result['you_can_join'] is False
    assert result['message'] == "Server full"
    assert result['capability'] == "+Freeciv-3.0-network"
    assert result['challenge_file'] == ""


@pytest.mark.unit
def test_decode_server_join_reply_empty_strings():
    """Test decoding JOIN_REPLY with empty message and challenge."""
    payload = (
        encode_bool(True) +
        encode_string("") +  # Empty message
        encode_string("+Freeciv-3.0-network") +
        encode_string("")  # Empty challenge
    )

    result = decode_server_join_reply(payload)

    assert result['you_can_join'] is True
    assert result['message'] == ""
    assert result['challenge_file'] == ""


@pytest.mark.unit
def test_decode_server_info_complete():
    """Test decoding SERVER_INFO packet with all fields."""
    # Build payload with all 5 fields
    payload = (
        encode_string("3.0.0") +
        encode_uint32(3) +
        encode_uint32(0) +
        encode_uint32(0) +
        encode_uint32(0)
    )

    result = decode_server_info(payload)

    assert result['version_label'] == "3.0.0"
    assert result['major_version'] == 3
    assert result['minor_version'] == 0
    assert result['patch_version'] == 0
    assert result['emerg_version'] == 0


@pytest.mark.unit
def test_decode_server_info_version_label():
    """Test SERVER_INFO handles various version label strings."""
    # Version with suffix
    payload = (
        encode_string("3.0.0-beta") +
        encode_uint32(3) +
        encode_uint32(0) +
        encode_uint32(0) +
        encode_uint32(0)
    )

    result = decode_server_info(payload)
    assert result['version_label'] == "3.0.0-beta"


@pytest.mark.unit
def test_decode_chat_msg_full_packet():
    """Test decoding CHAT_MSG with all 6 fields present."""
    # Build complete packet (no delta encoding)
    payload = (
        encode_string("Hello world!") +
        build_sint32_bytes(1000) +  # tile
        build_sint16_bytes(5) +  # event
        build_sint16_bytes(42) +  # turn
        build_sint16_bytes(0) +  # phase
        build_sint16_bytes(1)  # conn_id
    )

    result = decode_chat_msg(payload)

    assert result['message'] == "Hello world!"
    assert result['tile'] == 1000
    assert result['event'] == 5
    assert result['turn'] == 42
    assert result['phase'] == 0
    assert result['conn_id'] == 1


@pytest.mark.unit
def test_decode_chat_msg_omitted_fields():
    """Test legacy CHAT_MSG decoder when phase/conn_id are omitted."""
    # Build packet with only first 4 fields (simulating delta encoding)
    payload = (
        encode_string("Server message") +
        build_sint32_bytes(0) +  # tile
        build_sint16_bytes(0) +  # event
        build_sint16_bytes(1)  # turn
        # phase and conn_id omitted
    )

    result = decode_chat_msg(payload)

    assert result['message'] == "Server message"
    assert result['tile'] == 0
    assert result['event'] == 0
    assert result['turn'] == 1
    # Should use defaults for omitted fields
    assert result['phase'] == 0
    assert result['conn_id'] == -1


@pytest.mark.unit
def test_decode_chat_msg_empty_message():
    """Test CHAT_MSG with empty message string."""
    payload = (
        encode_string("") +  # Empty message
        build_sint32_bytes(0) +
        build_sint16_bytes(0) +
        build_sint16_bytes(0) +
        build_sint16_bytes(0) +
        build_sint16_bytes(-1)
    )

    result = decode_chat_msg(payload)
    assert result['message'] == ""


# ============================================================================
# Phase 4: Delta Protocol Helpers
# ============================================================================


# Bitvector tests (6 tests)


@pytest.mark.unit
def test_read_bitvector_single_byte():
    """Test reading bitvector with 8 bits or fewer (1 byte)."""
    # 8 bits = 1 byte
    data = b'\xb4extra'  # 10110100 in binary
    bitvector, offset = read_bitvector(data, 0, 8)
    assert bitvector == 0xb4
    assert offset == 1

    # 4 bits = still 1 byte (ceiling division)
    data = b'\x0fextra'
    bitvector, offset = read_bitvector(data, 0, 4)
    assert bitvector == 0x0f
    assert offset == 1


@pytest.mark.unit
def test_read_bitvector_multi_byte():
    """Test reading bitvector with 9-16 bits (2 bytes)."""
    # 9 bits = 2 bytes
    data = b'\x01\x80extra'
    bitvector, offset = read_bitvector(data, 0, 9)
    assert bitvector == 0x0180
    assert offset == 2

    # 16 bits = 2 bytes
    data = b'\xff\xffextra'
    bitvector, offset = read_bitvector(data, 0, 16)
    assert bitvector == 0xffff
    assert offset == 2


@pytest.mark.unit
def test_read_bitvector_offset_tracking():
    """Test that offset advances correctly for multi-byte bitvectors."""
    # 17 bits = 3 bytes
    data = b'\x12\x34\x56extra'
    bitvector, offset = read_bitvector(data, 0, 17)
    assert offset == 3

    # 24 bits = 3 bytes
    data = b'\xaa\xbb\xccextra'
    bitvector, offset = read_bitvector(data, 0, 24)
    assert bitvector == 0xaabbcc
    assert offset == 3


@pytest.mark.unit
def test_is_bit_set_various(sample_bitvector):
    """Test is_bit_set with sample_bitvector (0xB4 = 10110100)."""
    # Convert bytes to int
    bitvector = int.from_bytes(sample_bitvector, 'big')  # 0xb4 = 180

    # Bit pattern: 10110100 (LSB to MSB: bit 0 = 0, bit 1 = 0, bit 2 = 1, ...)
    assert is_bit_set(bitvector, 0) is False
    assert is_bit_set(bitvector, 1) is False
    assert is_bit_set(bitvector, 2) is True
    assert is_bit_set(bitvector, 3) is False
    assert is_bit_set(bitvector, 4) is True
    assert is_bit_set(bitvector, 5) is True
    assert is_bit_set(bitvector, 6) is False
    assert is_bit_set(bitvector, 7) is True


@pytest.mark.unit
def test_is_bit_set_all_zeros():
    """Test is_bit_set with bitvector of all zeros."""
    bitvector = 0
    for i in range(8):
        assert is_bit_set(bitvector, i) is False


@pytest.mark.unit
def test_is_bit_set_all_ones():
    """Test is_bit_set with bitvector of all ones."""
    bitvector = 0xFFFFFFFF
    for i in range(32):
        assert is_bit_set(bitvector, i) is True


# Field decoder tests (7 tests)


@pytest.mark.unit
def test_decode_field_string():
    """Test _decode_field with STRING type."""
    data = b'hello\x00extra'
    value, offset = _decode_field(data, 0, 'STRING')
    assert value == "hello"
    assert offset == 6


@pytest.mark.unit
def test_decode_field_bool():
    """Test _decode_field with BOOL type."""
    data = b'\x01extra'
    value, offset = _decode_field(data, 0, 'BOOL')
    assert value is True
    assert offset == 1


@pytest.mark.unit
def test_decode_field_uint32():
    """Test _decode_field with UINT32 type."""
    data = b'\x00\x00\x00\x2aextra'
    value, offset = _decode_field(data, 0, 'UINT32')
    assert value == 42
    assert offset == 4


@pytest.mark.unit
def test_decode_field_sint16():
    """Test _decode_field with SINT16 type."""
    data = b'\xff\xd6extra'  # -42
    value, offset = _decode_field(data, 0, 'SINT16')
    assert value == -42
    assert offset == 2


@pytest.mark.unit
def test_decode_field_sint32():
    """Test _decode_field with SINT32 type."""
    data = b'\xff\xff\xff\xd6extra'  # -42
    value, offset = _decode_field(data, 0, 'SINT32')
    assert value == -42
    assert offset == 4


@pytest.mark.unit
def test_decode_field_unsupported_type():
    """Test _decode_field raises ValueError for unsupported type."""
    data = b'\x00\x00\x00\x00'
    with pytest.raises(ValueError, match="Unsupported field type"):
        _decode_field(data, 0, 'UNSUPPORTED_TYPE')


@pytest.mark.unit
def test_decode_field_all_types():
    """Test _decode_field handles all supported types correctly."""
    # Build data with all types
    data = (
        encode_string("test") +  # STRING
        encode_bool(True) +  # BOOL
        encode_uint32(12345) +  # UINT32
        build_sint16_bytes(-100) +  # SINT16
        build_sint32_bytes(-999999)  # SINT32
    )

    offset = 0

    # STRING
    value, offset = _decode_field(data, offset, 'STRING')
    assert value == "test"

    # BOOL
    value, offset = _decode_field(data, offset, 'BOOL')
    assert value is True

    # UINT32
    value, offset = _decode_field(data, offset, 'UINT32')
    assert value == 12345

    # SINT16
    value, offset = _decode_field(data, offset, 'SINT16')
    assert value == -100

    # SINT32
    value, offset = _decode_field(data, offset, 'SINT32')
    assert value == -999999
