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
    encode_sint16,
    decode_sint16,
    decode_sint32,
    encode_uint8,
    encode_sint8,
    decode_uint8,
    decode_sint8,
    # Packet encoding
    encode_packet,
    encode_server_join_req,
    # Packet decoding
    decode_server_join_reply,
    decode_server_info,
    decode_chat_msg,
    decode_ruleset_summary,
    decode_ruleset_nation_sets,
    decode_ruleset_nation_groups,
    decode_nation_availability,
    decode_ruleset_achievement,
    decode_ruleset_trade,
    decode_ruleset_tech_flag,
    # Delta protocol helpers
    read_bitvector,
    is_bit_set,
    _decode_field,
    # Constants
    PACKET_SERVER_JOIN_REQ,
    PACKET_RULESET_TECH_FLAG,
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


# SINT16 encoding tests (3 tests)


@pytest.mark.unit
def test_encode_sint16_positive():
    """Test encoding positive SINT16 values."""
    result = encode_sint16(42)
    assert result == b'\x00\x2a'

    result = encode_sint16(1000)
    assert result == b'\x03\xe8'


@pytest.mark.unit
def test_encode_sint16_negative():
    """Test encoding negative SINT16 values."""
    result = encode_sint16(-42)
    assert result == b'\xff\xd6'

    result = encode_sint16(-1000)
    assert result == b'\xfc\x18'


@pytest.mark.unit
def test_encode_sint16_boundaries():
    """Test SINT16 boundary values (min=-32768, max=32767)."""
    # Min value: -32768
    result = encode_sint16(-32768)
    assert result == b'\x80\x00'

    # Max value: 32767
    result = encode_sint16(32767)
    assert result == b'\x7f\xff'

    # Zero
    result = encode_sint16(0)
    assert result == b'\x00\x00'


# UINT8 encoding/decoding tests (4 tests)


@pytest.mark.unit
def test_encode_uint8_basic():
    """Test encoding basic UINT8 values."""
    result = encode_uint8(0)
    assert result == b'\x00'

    result = encode_uint8(42)
    assert result == b'\x2a'

    result = encode_uint8(127)
    assert result == b'\x7f'


@pytest.mark.unit
def test_encode_uint8_boundaries():
    """Test UINT8 boundary values (min=0, max=255)."""
    # Min value: 0
    result = encode_uint8(0)
    assert result == b'\x00'

    # Max value: 255
    result = encode_uint8(255)
    assert result == b'\xff'


@pytest.mark.unit
def test_decode_uint8_basic():
    """Test decoding basic UINT8 values."""
    data = b'\x00extra'
    value, offset = decode_uint8(data, 0)
    assert value == 0
    assert offset == 1

    data = b'\x2aextra'
    value, offset = decode_uint8(data, 0)
    assert value == 42
    assert offset == 1

    data = b'\x7fextra'
    value, offset = decode_uint8(data, 0)
    assert value == 127
    assert offset == 1


@pytest.mark.unit
def test_decode_uint8_boundaries():
    """Test UINT8 boundary values (min=0, max=255)."""
    # Min value: 0
    data = b'\x00'
    value, offset = decode_uint8(data, 0)
    assert value == 0
    assert offset == 1

    # Max value: 255
    data = b'\xff'
    value, offset = decode_uint8(data, 0)
    assert value == 255
    assert offset == 1


# SINT8 encoding/decoding tests (6 tests)


@pytest.mark.unit
def test_encode_sint8_positive():
    """Test encoding positive SINT8 values."""
    result = encode_sint8(0)
    assert result == b'\x00'

    result = encode_sint8(42)
    assert result == b'\x2a'

    result = encode_sint8(127)
    assert result == b'\x7f'


@pytest.mark.unit
def test_encode_sint8_negative():
    """Test encoding negative SINT8 values."""
    result = encode_sint8(-1)
    assert result == b'\xff'

    result = encode_sint8(-42)
    assert result == b'\xd6'

    result = encode_sint8(-128)
    assert result == b'\x80'


@pytest.mark.unit
def test_encode_sint8_boundaries():
    """Test SINT8 boundary values (min=-128, max=127)."""
    # Min value: -128
    result = encode_sint8(-128)
    assert result == b'\x80'

    # Max value: 127
    result = encode_sint8(127)
    assert result == b'\x7f'

    # Zero
    result = encode_sint8(0)
    assert result == b'\x00'


@pytest.mark.unit
def test_decode_sint8_positive():
    """Test decoding positive SINT8 values."""
    data = b'\x00extra'
    value, offset = decode_sint8(data, 0)
    assert value == 0
    assert offset == 1

    data = b'\x2aextra'
    value, offset = decode_sint8(data, 0)
    assert value == 42
    assert offset == 1

    data = b'\x7fextra'
    value, offset = decode_sint8(data, 0)
    assert value == 127
    assert offset == 1


@pytest.mark.unit
def test_decode_sint8_negative():
    """Test decoding negative SINT8 values."""
    data = b'\xffextra'
    value, offset = decode_sint8(data, 0)
    assert value == -1
    assert offset == 1

    data = b'\xd6extra'
    value, offset = decode_sint8(data, 0)
    assert value == -42
    assert offset == 1

    data = b'\x80extra'
    value, offset = decode_sint8(data, 0)
    assert value == -128
    assert offset == 1


@pytest.mark.unit
def test_decode_sint8_boundaries():
    """Test SINT8 boundary values (min=-128, max=127)."""
    # Min value: -128
    data = b'\x80'
    value, offset = decode_sint8(data, 0)
    assert value == -128
    assert offset == 1

    # Max value: 127
    data = b'\x7f'
    value, offset = decode_sint8(data, 0)
    assert value == 127
    assert offset == 1

    # Zero
    data = b'\x00'
    value, offset = decode_sint8(data, 0)
    assert value == 0
    assert offset == 1


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
        encode_string("") +
        encode_sint16(1)  # conn_id
    )

    result = decode_server_join_reply(payload)

    assert result['you_can_join'] is True
    assert result['message'] == "Welcome!"
    assert result['capability'] == "+Freeciv-3.0-network"
    assert result['challenge_file'] == ""
    assert result['conn_id'] == 1


@pytest.mark.unit
def test_decode_server_join_reply_failure(sample_join_reply_failure):
    """Test decoding failed JOIN_REPLY packet."""
    # Build payload
    payload = (
        encode_bool(False) +
        encode_string("Server full") +
        encode_string("+Freeciv-3.0-network") +
        encode_string("") +
        encode_sint16(0)  # conn_id
    )

    result = decode_server_join_reply(payload)

    assert result['you_can_join'] is False
    assert result['message'] == "Server full"
    assert result['capability'] == "+Freeciv-3.0-network"
    assert result['challenge_file'] == ""
    assert result['conn_id'] == 0


@pytest.mark.unit
def test_decode_server_join_reply_empty_strings():
    """Test decoding JOIN_REPLY with empty message and challenge."""
    payload = (
        encode_bool(True) +
        encode_string("") +  # Empty message
        encode_string("+Freeciv-3.0-network") +
        encode_string("") +  # Empty challenge
        encode_sint16(1)  # conn_id
    )

    result = decode_server_join_reply(payload)

    assert result['you_can_join'] is True
    assert result['message'] == ""
    assert result['challenge_file'] == ""
    assert result['conn_id'] == 1


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
    # Note: bitvectors use little-endian byte order (FreeCiv protocol)
    data = b'\x01\x80extra'
    bitvector, offset = read_bitvector(data, 0, 9)
    assert bitvector == 0x8001  # little-endian: \x01\x80 -> 0x8001
    assert offset == 2

    # 16 bits = 2 bytes
    data = b'\xff\xffextra'
    bitvector, offset = read_bitvector(data, 0, 16)
    assert bitvector == 0xffff  # same in both endianness
    assert offset == 2


@pytest.mark.unit
def test_read_bitvector_offset_tracking():
    """Test that offset advances correctly for multi-byte bitvectors."""
    # 17 bits = 3 bytes
    data = b'\x12\x34\x56extra'
    bitvector, offset = read_bitvector(data, 0, 17)
    assert offset == 3

    # 24 bits = 3 bytes
    # Note: bitvectors use little-endian byte order (FreeCiv protocol)
    data = b'\xaa\xbb\xccextra'
    bitvector, offset = read_bitvector(data, 0, 24)
    assert bitvector == 0xccbbaa  # little-endian: \xaa\xbb\xcc -> 0xccbbaa
    assert offset == 3


@pytest.mark.unit
def test_is_bit_set_various(sample_bitvector):
    """Test is_bit_set with sample_bitvector (0xB4 = 10110100)."""
    # Convert bytes to int (for single byte, endianness doesn't matter)
    bitvector = int.from_bytes(sample_bitvector, 'little')  # 0xb4 = 180

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


# ============================================================================
# PACKET_RULESET_SUMMARY Decoder Tests
# ============================================================================


@pytest.mark.unit
def test_decode_ruleset_summary_simple():
    """Test decoding RULESET_SUMMARY with simple text."""
    text = "Classic ruleset with standard game mechanics."
    payload = encode_string(text)

    result = decode_ruleset_summary(payload)

    assert result['text'] == text


@pytest.mark.unit
def test_decode_ruleset_summary_empty():
    """Test decoding RULESET_SUMMARY with empty string."""
    payload = encode_string("")

    result = decode_ruleset_summary(payload)

    assert result['text'] == ""


@pytest.mark.unit
def test_decode_ruleset_summary_long():
    """Test decoding RULESET_SUMMARY with near-maximum length (4000 chars)."""
    # Create a long text (4000 chars, approaching the 4076 byte limit)
    text = "A" * 4000

    payload = encode_string(text)

    result = decode_ruleset_summary(payload)

    assert result['text'] == text
    assert len(result['text']) == 4000


@pytest.mark.unit
def test_decode_ruleset_summary_multiline():
    """Test decoding RULESET_SUMMARY with newlines preserved."""
    text = "Line 1\nLine 2\nLine 3\n\nLine 5 after blank line"
    payload = encode_string(text)

    result = decode_ruleset_summary(payload)

    assert result['text'] == text
    assert "\n" in result['text']
    assert result['text'].count("\n") == 4


@pytest.mark.unit
def test_decode_ruleset_summary_unicode():
    """Test decoding RULESET_SUMMARY with UTF-8 characters (emoji, international)."""
    # Emoji
    text_emoji = "This ruleset is awesome! 🎮🎲🏰"
    payload = encode_string(text_emoji)
    result = decode_ruleset_summary(payload)
    assert result['text'] == text_emoji

    # International characters (Chinese, Arabic, Cyrillic)
    text_intl = "欢迎 مرحبا Добро пожаловать"
    payload = encode_string(text_intl)
    result = decode_ruleset_summary(payload)
    assert result['text'] == text_intl

    # Combined
    text_combined = "Freeciv 🌍 世界征服 Завоевание мира"
    payload = encode_string(text_combined)
    result = decode_ruleset_summary(payload)
    assert result['text'] == text_combined


# PACKET_RULESET_NATION_SETS Tests

def test_decode_ruleset_nation_sets_empty():
    """Test decoding packet with nsets=0."""
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x00'  # nsets=0
    )
    result = decode_ruleset_nation_sets(payload)
    assert result['nsets'] == 0
    assert result['names'] == []
    assert result['rule_names'] == []
    assert result['descriptions'] == []


def test_decode_ruleset_nation_sets_single():
    """Test decoding packet with single nation set using delta protocol."""
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x01'  # nsets=1
        # Null-terminated variable-length strings (not fixed-size)
        b'Core\x00'  # names[0]
        b'core\x00'  # rule_names[0]
        b'Default nations\x00'  # descriptions[0]
    )
    result = decode_ruleset_nation_sets(payload)
    assert result['nsets'] == 1
    assert result['names'] == ['Core']
    assert result['rule_names'] == ['core']
    assert result['descriptions'] == ['Default nations']


def test_decode_ruleset_nation_sets_multiple():
    """Test decoding packet with multiple nation sets using delta protocol."""
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x03'  # nsets=3
        # Null-terminated variable-length strings (not fixed-size)
        # names[3]
        b'Core\x00'
        b'Extended\x00'
        b'Custom\x00'
        # rule_names[3]
        b'core\x00'
        b'extended\x00'
        b'custom\x00'
        # descriptions[3]
        b'Default\x00'
        b'Additional\x00'
        b'User-created\x00'
    )
    result = decode_ruleset_nation_sets(payload)
    assert result['nsets'] == 3
    assert result['names'] == ['Core', 'Extended', 'Custom']
    assert result['rule_names'] == ['core', 'extended', 'custom']
    assert result['descriptions'] == ['Default', 'Additional', 'User-created']


def test_decode_ruleset_nation_sets_empty_strings():
    """Test decoding packet with empty string fields using delta protocol."""
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x01'  # nsets=1
        # Null-terminated variable-length strings (not fixed-size)
        b'\x00'  # empty name
        b'core\x00'  # rule_name
        b'\x00'  # empty description
    )
    result = decode_ruleset_nation_sets(payload)
    assert result['nsets'] == 1
    assert result['names'] == ['']
    assert result['rule_names'] == ['core']
    assert result['descriptions'] == ['']


def test_decode_ruleset_nation_sets_unicode():
    """Test decoding packet with UTF-8 unicode strings using delta protocol."""
    payload = (
        b'\x0F'  # bitvector: all 4 fields present (bits 0-3 set)
        b'\x01'  # nsets=1
        # Null-terminated variable-length strings (not fixed-size)
        b'Na\xc3\xa7\xc3\xb5es\x00'  # names[0] - "Nações" in UTF-8
        b'nacoes\x00'  # rule_names[0]
        b'Description\x00'  # descriptions[0]
    )
    result = decode_ruleset_nation_sets(payload)
    assert result['names'] == ['Nações']


# ============================================================================
# PACKET_RULESET_NATION_GROUPS Tests
# ============================================================================

def test_decode_ruleset_nation_groups_empty():
    """Test decoding packet with ngroups=0."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x00'  # ngroups=0
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 0
    assert result['groups'] == []
    assert result['hidden'] == []


def test_decode_ruleset_nation_groups_single():
    """Test decoding packet with single nation group using delta protocol."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x01'  # ngroups=1
        # Null-terminated variable-length string
        b'?nationgroup:Ancient\x00'  # groups[0]
        b'\x00'  # hidden[0]=false (visible)
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 1
    assert result['groups'] == ['?nationgroup:Ancient']
    assert result['hidden'] == [False]


def test_decode_ruleset_nation_groups_multiple():
    """Test decoding packet with multiple nation groups using delta protocol."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x03'  # ngroups=3
        # Null-terminated variable-length strings
        b'?nationgroup:Ancient\x00'
        b'?nationgroup:Medieval\x00'
        b'?nationgroup:Modern\x00'
        # hidden array (boolean values, 1 byte each)
        b'\x00'  # hidden[0]=false
        b'\x00'  # hidden[1]=false
        b'\x00'  # hidden[2]=false
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 3
    assert result['groups'] == [
        '?nationgroup:Ancient',
        '?nationgroup:Medieval',
        '?nationgroup:Modern'
    ]
    assert result['hidden'] == [False, False, False]


def test_decode_ruleset_nation_groups_all_visible():
    """Test decoding packet with all groups visible (hidden=false)."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present
        b'\x02'  # ngroups=2
        b'Ancient\x00'
        b'Modern\x00'
        b'\x00'  # hidden[0]=false
        b'\x00'  # hidden[1]=false
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 2
    assert result['hidden'] == [False, False]


def test_decode_ruleset_nation_groups_all_hidden():
    """Test decoding packet with all groups hidden (hidden=true)."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present
        b'\x02'  # ngroups=2
        b'Test1\x00'
        b'Test2\x00'
        b'\x01'  # hidden[0]=true
        b'\x01'  # hidden[1]=true
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 2
    assert result['hidden'] == [True, True]


def test_decode_ruleset_nation_groups_mixed_visibility():
    """Test decoding packet with mixed visibility (some visible, some hidden)."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present
        b'\x04'  # ngroups=4
        b'Ancient\x00'
        b'Medieval\x00'
        b'Modern\x00'
        b'Barbarian\x00'
        b'\x00'  # hidden[0]=false (visible)
        b'\x00'  # hidden[1]=false (visible)
        b'\x00'  # hidden[2]=false (visible)
        b'\x01'  # hidden[3]=true (hidden)
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 4
    assert result['groups'] == ['Ancient', 'Medieval', 'Modern', 'Barbarian']
    assert result['hidden'] == [False, False, False, True]


def test_decode_ruleset_nation_groups_empty_strings():
    """Test decoding packet with empty group names."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present
        b'\x01'  # ngroups=1
        b'\x00'  # empty group name
        b'\x00'  # hidden=false
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 1
    assert result['groups'] == ['']
    assert result['hidden'] == [False]


def test_decode_ruleset_nation_groups_unicode():
    """Test decoding packet with UTF-8 unicode strings."""
    payload = (
        b'\x07'  # bitvector: all 3 fields present
        b'\x01'  # ngroups=1
        # "Européen" in UTF-8
        b'Europ\xc3\xa9en\x00'
        b'\x00'  # hidden=false
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 1
    assert result['groups'] == ['Européen']
    assert result['hidden'] == [False]


def test_decode_ruleset_nation_groups_from_captured_packet():
    """Test decoding actual captured packet from packets/inbound_19.packet."""
    # This is the actual payload from the captured packet (excluding 4-byte header)
    # Header was: 0x0102 (length=258) 0x0093 (type=147)
    # Payload contains 11 nation groups with the last one (Barbarian) hidden
    payload = (
        b'\x07'  # bitvector: all 3 fields present (bits 0-2 set)
        b'\x0b'  # ngroups=11
        # 11 null-terminated strings
        b'?nationgroup:Ancient\x00'
        b'?nationgroup:Medieval\x00'
        b'?nationgroup:Early Modern\x00'
        b'?nationgroup:Modern\x00'
        b'?nationgroup:African\x00'
        b'?nationgroup:American\x00'
        b'?nationgroup:Asian\x00'
        b'?nationgroup:European\x00'
        b'?nationgroup:Oceanian\x00'
        b'?nationgroup:Imaginary\x00'
        b'?nationgroup:Barbarian\x00'
        # 11 boolean values (1 byte each)
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01'
    )
    result = decode_ruleset_nation_groups(payload)
    assert result['ngroups'] == 11
    assert len(result['groups']) == 11
    assert result['groups'][0] == '?nationgroup:Ancient'
    assert result['groups'][1] == '?nationgroup:Medieval'
    assert result['groups'][2] == '?nationgroup:Early Modern'
    assert result['groups'][3] == '?nationgroup:Modern'
    assert result['groups'][4] == '?nationgroup:African'
    assert result['groups'][5] == '?nationgroup:American'
    assert result['groups'][6] == '?nationgroup:Asian'
    assert result['groups'][7] == '?nationgroup:European'
    assert result['groups'][8] == '?nationgroup:Oceanian'
    assert result['groups'][9] == '?nationgroup:Imaginary'
    assert result['groups'][10] == '?nationgroup:Barbarian'
    # First 10 are visible (false), last one is hidden (true)
    assert result['hidden'] == [False, False, False, False, False,
                                 False, False, False, False, False, True]


# ============================================================================
# PACKET_NATION_AVAILABILITY Tests (5 tests)
# ============================================================================


@pytest.mark.unit
def test_decode_nation_availability_basic():
    """Test decoding basic nation availability packet with 3 nations using delta protocol."""
    payload = (
        b'\x03'      # bitvector: bits 0,1 set (ncount and is_pickable present), bit 2 clear (nationset_change=False)
        b'\x00\x03'  # ncount=3 (UINT16, big-endian)
        b'\x01'      # is_pickable[0]=True
        b'\x00'      # is_pickable[1]=False
        b'\x01'      # is_pickable[2]=True
    )
    result = protocol.decode_nation_availability(payload)
    assert result['ncount'] == 3
    assert result['is_pickable'] == [True, False, True]
    assert result['nationset_change'] is False


@pytest.mark.unit
def test_decode_nation_availability_empty():
    """Test decoding packet with zero nations (edge case)."""
    payload = (
        b'\x07'      # bitvector: bits 0,1,2 set (all fields present, nationset_change=True via folding)
        b'\x00\x00'  # ncount=0 (UINT16, big-endian)
        # No is_pickable array bytes (ncount=0)
    )
    result = protocol.decode_nation_availability(payload)
    assert result['ncount'] == 0
    assert result['is_pickable'] == []
    assert result['nationset_change'] is True


@pytest.mark.unit
def test_decode_nation_availability_large():
    """Test decoding packet with realistic number of nations (52 nations)."""
    ncount = 52
    # Create payload with 52 nations, alternating availability
    is_pickable_bytes = bytes([i % 2 for i in range(ncount)])

    payload = (
        b'\x03' +                              # bitvector: bits 0,1 set, bit 2 clear (nationset_change=False)
        struct.pack('>H', ncount) +            # ncount=52 (UINT16, big-endian)
        is_pickable_bytes                      # 52 BOOL values
    )

    result = protocol.decode_nation_availability(payload)
    assert result['ncount'] == 52
    assert len(result['is_pickable']) == 52
    # Check first few values
    assert result['is_pickable'][0] is False  # 0 % 2 = 0
    assert result['is_pickable'][1] is True   # 1 % 2 = 1
    assert result['is_pickable'][2] is False  # 2 % 2 = 0
    assert result['is_pickable'][3] is True   # 3 % 2 = 1
    assert result['nationset_change'] is False


@pytest.mark.unit
def test_decode_nation_availability_nationset_change():
    """Test decoding packet with nationset_change flag set via boolean header folding."""
    payload = (
        b'\x07'      # bitvector: bits 0,1,2 set (all fields present, nationset_change=True)
        b'\x00\x02'  # ncount=2 (UINT16, big-endian)
        b'\x01'      # is_pickable[0]=True
        b'\x01'      # is_pickable[1]=True
    )
    result = protocol.decode_nation_availability(payload)
    assert result['ncount'] == 2
    assert result['is_pickable'] == [True, True]
    assert result['nationset_change'] is True


@pytest.mark.unit
def test_decode_nation_availability_from_captured_packet():
    """Test decoding actual captured packet from real server (572 nations)."""
    # This is the actual payload from captured packet inbound_0592_type237.packet
    # Bitvector 0x03 = bits 0,1 set (ncount and is_pickable present)
    # ncount = 0x023c = 572 (big-endian)

    # Build payload: bitvector (1) + ncount (2) + is_pickable array (572)
    bitvector = b'\x03'  # Bits 0,1 set, bit 2 clear
    ncount_bytes = b'\x02\x3c'  # 572 in big-endian (0x023c)
    is_pickable_bytes = b'\x00' * 572  # All nations unavailable
    payload = bitvector + ncount_bytes + is_pickable_bytes

    result = protocol.decode_nation_availability(payload)
    assert result['ncount'] == 572
    assert len(result['is_pickable']) == 572
    assert result['nationset_change'] is False  # Bit 2 not set
    # First few nations should be unavailable in this test
    assert result['is_pickable'][0] is False


def test_decode_ruleset_game_minimal():
    """Test decode_ruleset_game with minimal configuration (1 veteran level)."""
    # Build payload with actual observed structure
    # 4 unknown bytes (purpose unclear)
    payload = struct.pack('<BBBB', 248, 63, 1, 23)

    # veteran_levels
    payload += struct.pack('<B', 1)  # veteran_levels

    # 1 veteran level: name
    payload += b'Green\x00'  # veteran_name[0]

    # 1 veteran level: power_fact (UINT16)
    payload += struct.pack('>H', 100)  # power_fact[0]

    # 1 veteran level: move_bonus (MOVEFRAGS = UINT32)
    payload += struct.pack('>I', 0)  # move_bonus[0]

    # 1 veteran level: base_raise_chance
    payload += struct.pack('<B', 50)  # base_raise_chance[0]

    # 1 veteran level: work_raise_chance
    payload += struct.pack('<B', 0)  # work_raise_chance[0]

    # Background color (RGB)
    payload += struct.pack('<BBB', 139, 140, 141)  # background_red, green, blue

    result = protocol.decode_ruleset_game(payload)
    assert result['default_specialist'] == 0
    assert result['global_init_techs_count'] == 0
    assert result['global_init_techs'] == []
    assert result['global_init_buildings_count'] == 0
    assert result['global_init_buildings'] == []
    assert result['veteran_levels'] == 1
    assert result['veteran_name'] == ['Green']
    assert result['power_fact'] == [100]
    assert result['move_bonus'] == [0]
    assert result['base_raise_chance'] == [50]
    assert result['work_raise_chance'] == [0]
    assert result['background_red'] == 139
    assert result['background_green'] == 140
    assert result['background_blue'] == 141


def test_decode_ruleset_game_with_techs_and_buildings():
    """Test decode_ruleset_game with multiple veteran levels."""
    # Build payload with actual observed structure
    # 4 unknown bytes
    payload = struct.pack('<BBBB', 248, 63, 1, 23)

    # 2 veteran levels
    payload += struct.pack('<B', 2)  # veteran_levels

    # Veteran names
    payload += b'Rookie\x00'  # veteran_name[0]
    payload += b'Veteran\x00'  # veteran_name[1]

    # Power factors
    payload += struct.pack('>H', 100)  # power_fact[0]
    payload += struct.pack('>H', 150)  # power_fact[1]

    # Move bonuses
    payload += struct.pack('>I', 0)  # move_bonus[0]
    payload += struct.pack('>I', 3)  # move_bonus[1]

    # Base raise chances
    payload += struct.pack('<B', 50)  # base_raise_chance[0]
    payload += struct.pack('<B', 33)  # base_raise_chance[1]

    # Work raise chances
    payload += struct.pack('<B', 0)  # work_raise_chance[0]
    payload += struct.pack('<B', 0)  # work_raise_chance[1]

    # Background color
    payload += struct.pack('<BBB', 255, 255, 255)

    result = protocol.decode_ruleset_game(payload)
    # Tech/building fields not in actual packet (set to defaults)
    assert result['default_specialist'] == 0
    assert result['global_init_techs_count'] == 0
    assert result['global_init_techs'] == []
    assert result['global_init_buildings_count'] == 0
    assert result['global_init_buildings'] == []
    assert result['veteran_levels'] == 2
    assert result['veteran_name'] == ['Rookie', 'Veteran']
    assert result['power_fact'] == [100, 150]
    assert result['move_bonus'] == [0, 3]
    assert result['base_raise_chance'] == [50, 33]
    assert result['work_raise_chance'] == [0, 0]
    assert result['background_red'] == 255
    assert result['background_green'] == 255
    assert result['background_blue'] == 255


def test_decode_ruleset_game_max_veteran_levels():
    """Test decode_ruleset_game with maximum realistic veteran levels."""
    # Build payload with actual observed structure
    # 4 unknown bytes
    payload = struct.pack('<BBBB', 248, 63, 1, 23)

    # 10 veteran levels
    veteran_count = 10
    payload += struct.pack('<B', veteran_count)

    # Veteran names
    names = ['Green', 'Rookie', 'Veteran', 'Hardened', 'Elite',
             'Champion', 'Legendary', 'Hero', 'Immortal', 'Divine']
    for name in names:
        payload += name.encode('utf-8') + b'\x00'

    # Power factors (increasing)
    for i in range(veteran_count):
        payload += struct.pack('>H', 100 + i * 10)

    # Move bonuses (increasing)
    for i in range(veteran_count):
        payload += struct.pack('>I', i)

    # Base raise chances (decreasing)
    for i in range(veteran_count):
        payload += struct.pack('<B', max(0, 50 - i * 5))

    # Work raise chances (decreasing)
    for i in range(veteran_count):
        payload += struct.pack('<B', max(0, 20 - i * 2))

    # Background color
    payload += struct.pack('<BBB', 50, 100, 150)

    result = protocol.decode_ruleset_game(payload)
    assert result['default_specialist'] == 0
    assert result['global_init_techs_count'] == 0
    assert result['global_init_buildings_count'] == 0
    assert result['veteran_levels'] == 10
    assert result['veteran_name'] == names
    assert result['power_fact'] == [100 + i * 10 for i in range(10)]
    assert result['move_bonus'] == list(range(10))
    assert result['base_raise_chance'] == [max(0, 50 - i * 5) for i in range(10)]
    assert result['work_raise_chance'] == [max(0, 20 - i * 2) for i in range(10)]
    assert result['background_red'] == 50
    assert result['background_green'] == 100
    assert result['background_blue'] == 150


@pytest.mark.unit
def test_decode_ruleset_achievement_real_packet():
    """Test with real captured packet from FreeCiv 3.2 server.

    This proves packets.def is WRONG - there is no 'value' field!
    Source: inbound_0599_type233.packet
    """
    # Real captured payload (minus length/type header)
    payload = bytes([
        0x26,  # id = 38
        # name = "Spaceship Launch"
        0x53, 0x70, 0x61, 0x63, 0x65, 0x73, 0x68, 0x69, 0x70, 0x20,
        0x4c, 0x61, 0x75, 0x6e, 0x63, 0x68, 0x00,
        # rule_name = "Spaceship Launch"
        0x53, 0x70, 0x61, 0x63, 0x65, 0x73, 0x68, 0x69, 0x70, 0x20,
        0x4c, 0x61, 0x75, 0x6e, 0x63, 0x68, 0x00,
        0x00,  # type = 0 (ACHIEVEMENT_SPACESHIP)
        0x01   # unique = True
    ])

    result = decode_ruleset_achievement(payload)

    assert result['id'] == 38
    assert result['name'] == "Spaceship Launch"
    assert result['rule_name'] == "Spaceship Launch"
    assert result['type'] == 0
    assert result['unique'] is True


@pytest.mark.unit
def test_decode_ruleset_achievement_minimal():
    """Test with minimal synthetic data."""
    payload = (
        encode_uint8(0) +
        encode_string("Test") +
        encode_string("test") +
        encode_uint8(1) +
        encode_bool(False)
    )

    result = decode_ruleset_achievement(payload)

    assert result['id'] == 0
    assert result['name'] == "Test"
    assert result['rule_name'] == "test"
    assert result['type'] == 1
    assert result['unique'] is False


def test_decode_ruleset_trade():
    """Test decoding PACKET_RULESET_TRADE with delta protocol."""
    # bitvector=0x0F (all 4 bits set), id=1, trade_pct=150, cancelling=2, bonus_type=3
    payload = bytes([
        0x0F,       # bitvector (bits 0,1,2,3 all set)
        1,          # id
        0, 150,     # trade_pct (big-endian UINT16)
        2,          # cancelling
        3,          # bonus_type
    ])

    result = decode_ruleset_trade(payload)

    assert result['id'] == 1
    assert result['trade_pct'] == 150
    assert result['cancelling'] == 2
    assert result['bonus_type'] == 3


def test_decode_ruleset_trade_partial():
    """Test decoding PACKET_RULESET_TRADE with partial fields (delta)."""
    # Real packet example: bitvector=0x0B (bits 0,1,3), id=2, trade_pct=100, bonus_type=1
    payload = bytes([
        0x0B,       # bitvector (bits 0,1,3 set, bit 2 clear)
        2,          # id
        0, 100,     # trade_pct (big-endian UINT16)
        1,          # bonus_type
    ])

    result = decode_ruleset_trade(payload)

    assert result['id'] == 2
    assert result['trade_pct'] == 100
    assert result['cancelling'] == 0  # Not transmitted, uses default
    assert result['bonus_type'] == 1

def test_decode_ruleset_action_from_captured_packet():
    """Test decoding PACKET_RULESET_ACTION (246) with real server data.

    Uses captured packet from packets/inbound_0617_type246.packet.
    Bitvector 0x0402 (bits 1, 10 set) indicates:
    - Bit 1: ui_name present ("Establish %sEmbassy%s")
    - Bit 10: max_distance present (1)
    """
    # Real packet payload (minus 4-byte header: 2 bytes length + 2 bytes type)
    # Hex: 02 04 "Establish %sEmbassy%s\0" 00 00 00 01
    payload = (
        b'\x02\x04'  # Bitvector: 0x0402 (bits 1, 10)
        b'Establish %sEmbassy%s\x00'  # ui_name (23 bytes with null terminator)
        b'\x00\x00\x00\x01'  # max_distance: 1 (sint32, big-endian)
    )
    
    result = protocol.decode_ruleset_action(payload)
    
    # Verify all fields
    assert result['id'] == 0  # Not transmitted, using default
    assert result['ui_name'] == 'Establish %sEmbassy%s'
    assert result['quiet'] is False
    assert result['result'] == 0
    assert result['sub_results'] == 0
    assert result['actor_consuming_always'] is False
    assert result['act_kind'] == 0
    assert result['tgt_kind'] == 0
    assert result['sub_tgt_kind'] == 0
    assert result['min_distance'] == 0
    assert result['max_distance'] == 1
    assert result['blocked_by'] == 0


def test_decode_ruleset_action_with_boolean_header_folding():
    """Test boolean header folding for quiet and actor_consuming_always fields.
    
    Bits 2 and 5 are header-folded booleans - their bitvector bit IS the value,
    consuming NO payload bytes.
    """
    # Bitvector: 0x24 = 0010 0100 (bits 2 and 5 set)
    # Bit 2: quiet = True (header-folded)
    # Bit 5: actor_consuming_always = True (header-folded)
    payload = b'\x24\x00'  # 2-byte bitvector, no other fields
    
    result = protocol.decode_ruleset_action(payload)
    
    assert result['quiet'] is True
    assert result['actor_consuming_always'] is True
    # All other fields should be defaults
    assert result['id'] == 0
    assert result['ui_name'] == ''


def test_decode_ruleset_action_with_bitvectors():
    """Test decoding bitvector fields (sub_results and blocked_by)."""
    # Bitvector: 0x0810 = 0001 0000 0001 0000 (bits 4 and 11 set)
    # Bit 4: sub_results (1 byte, 4 bits)
    # Bit 11: blocked_by (16 bytes, 128 bits)
    payload = (
        b'\x10\x08'  # Main bitvector: 0x0810
        b'\x0A'  # sub_results: 0x0A = bits 1 and 3 set
        b'\xFF\x00\x00\x00\x00\x00\x00\x00'  # blocked_by bytes 0-7
        b'\x00\x00\x00\x00\x00\x00\x00\x01'  # blocked_by bytes 8-15 (bit 120 set)
    )
    
    result = protocol.decode_ruleset_action(payload)
    
    assert result['sub_results'] == 0x0A
    # blocked_by: 0xFF in byte 0 = bits 0-7, bit 120 in byte 15
    expected_blocked_by = 0xFF | (1 << 120)
    assert result['blocked_by'] == expected_blocked_by


def test_decode_ruleset_action_all_fields():
    """Test decoding with all fields present."""
    # Bitvector: 0x0FFF = all 12 bits set
    payload = (
        b'\xFF\x0F'  # Bitvector: 0x0FFF (all 12 bits)
        b'\x2A'  # id: 42
        b'Test Action\x00'  # ui_name
        # Bit 2 (quiet) is True (header-folded)
        b'\x05'  # result: 5
        b'\x03'  # sub_results: 3 (1 byte)
        # Bit 5 (actor_consuming_always) is True (header-folded)
        b'\x01'  # act_kind: 1 (Player)
        b'\x02'  # tgt_kind: 2 (Units)
        b'\x00'  # sub_tgt_kind: 0
        b'\x00\x00\x00\x01'  # min_distance: 1 (sint32, big-endian)
        b'\x00\x00\x00\x05'  # max_distance: 5 (sint32, big-endian)
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'  # blocked_by: 16 bytes of zeros
    )
    
    result = protocol.decode_ruleset_action(payload)
    
    assert result['id'] == 42
    assert result['ui_name'] == 'Test Action'
    assert result['quiet'] is True
    assert result['result'] == 5
    assert result['sub_results'] == 3
    assert result['actor_consuming_always'] is True
    assert result['act_kind'] == 1
    assert result['tgt_kind'] == 2
    assert result['sub_tgt_kind'] == 0
    assert result['min_distance'] == 1
    assert result['max_distance'] == 5
    assert result['blocked_by'] == 0


def test_decode_ruleset_action_auto_from_captured_packet(delta_cache):
    """Test decoding PACKET_RULESET_ACTION_AUTO (252) with real server data.

    Uses captured packet from packets/inbound_0827_type252.packet.
    Bitvector 0x0c (bits 2, 3 set) indicates:
    - Bit 2: reqs_count present (2)
    - Bit 3: reqs array present (2 requirements)

    Other fields (id, cause, alternatives_count, alternatives) use cache/defaults.
    """
    # Real packet payload (minus 4-byte header)
    # Hex: 0c 02 0a 00 00 00 00 00 00 01 01 07 00 00 00 11 00 00 00 01
    payload = (
        b'\x0c'  # Bitvector: 0x0c (bits 2, 3)
        b'\x02'  # reqs_count: 2
        # Requirement 1 (9 bytes): type=10, value=0, range=0, survives=False, present=True, quiet=True
        b'\x0a'  # type: 10
        b'\x00\x00\x00\x00'  # value: 0 (sint32 big-endian)
        b'\x00'  # range: 0
        b'\x00'  # survives: False
        b'\x01'  # present: True
        b'\x01'  # quiet: True
        # Requirement 2 (9 bytes): type=7, value=17, range=0, survives=False, present=False, quiet=True
        b'\x07'  # type: 7
        b'\x00\x00\x00\x11'  # value: 17 (sint32 big-endian: 0x00000011)
        b'\x00'  # range: 0
        b'\x00'  # survives: False
        b'\x00'  # present: False
        b'\x01'  # quiet: True
    )

    result = protocol.decode_ruleset_action_auto(payload, delta_cache)

    # Verify fields
    assert result['id'] == 0  # Not transmitted, using default
    assert result['cause'] == 0  # Not transmitted, using default
    assert result['reqs_count'] == 2
    assert len(result['reqs']) == 2
    assert result['alternatives_count'] == 0  # Not transmitted, using default
    assert result['alternatives'] == []  # Not transmitted, using default

    # Verify requirement 1
    req1 = result['reqs'][0]
    assert req1['type'] == 10
    assert req1['value'] == 0
    assert req1['range'] == 0
    assert req1['survives'] is False
    assert req1['present'] is True
    assert req1['quiet'] is True

    # Verify requirement 2
    req2 = result['reqs'][1]
    assert req2['type'] == 7
    assert req2['value'] == 17  # 0x00000011 in big-endian
    assert req2['range'] == 0
    assert req2['survives'] is False
    assert req2['present'] is False
    assert req2['quiet'] is True


def test_decode_ruleset_action_auto_all_fields(delta_cache):
    """Test decoding PACKET_RULESET_ACTION_AUTO with all fields present."""
    # Bitvector: 0x3f (all 6 bits set)
    payload = (
        b'\x3f'  # Bitvector: 0x3f (bits 0-5 all set)
        b'\x05'  # id: 5
        b'\x02'  # cause: 2 (POST_ACTION)
        b'\x01'  # reqs_count: 1
        # Requirement (9 bytes): type=3, value=42, range=1, survives=True, present=True, quiet=False
        b'\x03'  # type: 3
        b'\x00\x00\x00\x2a'  # value: 42 (sint32 big-endian)
        b'\x01'  # range: 1
        b'\x01'  # survives: True
        b'\x01'  # present: True
        b'\x00'  # quiet: False
        b'\x03'  # alternatives_count: 3
        b'\x0a'  # alternative[0]: 10
        b'\x0b'  # alternative[1]: 11
        b'\x0c'  # alternative[2]: 12
    )

    result = protocol.decode_ruleset_action_auto(payload, delta_cache)

    # Verify all fields
    assert result['id'] == 5
    assert result['cause'] == 2
    assert result['reqs_count'] == 1
    assert len(result['reqs']) == 1
    assert result['alternatives_count'] == 3
    assert result['alternatives'] == [10, 11, 12]

    # Verify requirement
    req = result['reqs'][0]
    assert req['type'] == 3
    assert req['value'] == 42
    assert req['range'] == 1
    assert req['survives'] is True
    assert req['present'] is True
    assert req['quiet'] is False


# ============================================================================
# PACKET_RULESET_TECH_FLAG Tests
# ============================================================================


@pytest.mark.unit
def test_decode_ruleset_tech_flag_all_fields(delta_cache):
    """Test decoding PACKET_RULESET_TECH_FLAG with all fields present (no cache)."""
    # Bitvector: 0x07 (bits 0, 1, 2 set)
    payload = (
        b'\x07'  # All 3 bits set
        b'\x05'  # id: 5
        b'Bonus_Tech\x00'  # name
        b'This flag grants bonus research points.\x00'  # helptxt
    )

    result = decode_ruleset_tech_flag(payload, delta_cache)

    assert result['id'] == 5
    assert result['name'] == 'Bonus_Tech'
    assert result['helptxt'] == 'This flag grants bonus research points.'


@pytest.mark.unit
def test_decode_ruleset_tech_flag_delta_id_only(delta_cache):
    """Test delta update with only id changing."""
    # First packet: populate cache
    payload1 = (
        b'\x07'  # All fields present
        b'\x01'  # id: 1
        b'Tech_A\x00'
        b'Help text A\x00'
    )
    result1 = decode_ruleset_tech_flag(payload1, delta_cache)

    # Second packet: only id changes (bit 0)
    payload2 = (
        b'\x01'  # Only bit 0 set
        b'\x02'  # id: 2
    )
    result2 = decode_ruleset_tech_flag(payload2, delta_cache)

    assert result2['id'] == 2  # New value
    assert result2['name'] == 'Tech_A'  # From cache
    assert result2['helptxt'] == 'Help text A'  # From cache


@pytest.mark.unit
def test_decode_ruleset_tech_flag_delta_name_only(delta_cache):
    """Test delta update with only name changing."""
    # First packet: populate cache
    payload1 = (
        b'\x07'  # All fields present
        b'\x03'  # id: 3
        b'Original_Name\x00'
        b'Original help\x00'
    )
    decode_ruleset_tech_flag(payload1, delta_cache)

    # Second packet: only name changes (bit 1)
    payload2 = (
        b'\x02'  # Only bit 1 set
        b'Updated_Name\x00'
    )
    result2 = decode_ruleset_tech_flag(payload2, delta_cache)

    assert result2['id'] == 3  # From cache
    assert result2['name'] == 'Updated_Name'  # New value
    assert result2['helptxt'] == 'Original help'  # From cache


@pytest.mark.unit
def test_decode_ruleset_tech_flag_delta_helptxt_only(delta_cache):
    """Test delta update with only helptxt changing."""
    # First packet: populate cache
    payload1 = (
        b'\x07'  # All fields present
        b'\x04'  # id: 4
        b'Flag_Name\x00'
        b'Initial description\x00'
    )
    decode_ruleset_tech_flag(payload1, delta_cache)

    # Second packet: only helptxt changes (bit 2)
    payload2 = (
        b'\x04'  # Only bit 2 set
        b'Updated description with more details\x00'
    )
    result2 = decode_ruleset_tech_flag(payload2, delta_cache)

    assert result2['id'] == 4  # From cache
    assert result2['name'] == 'Flag_Name'  # From cache
    assert result2['helptxt'] == 'Updated description with more details'  # New value


@pytest.mark.unit
def test_decode_ruleset_tech_flag_delta_multiple_fields(delta_cache):
    """Test delta update with multiple fields changing."""
    # First packet: populate cache
    payload1 = (
        b'\x07'  # All fields present
        b'\x10'  # id: 16
        b'Flag1\x00'
        b'Help1\x00'
    )
    decode_ruleset_tech_flag(payload1, delta_cache)

    # Second packet: id and name change (bits 0, 1)
    payload2 = (
        b'\x03'  # Bits 0 and 1 set
        b'\x11'  # id: 17
        b'Flag2\x00'  # name
    )
    result2 = decode_ruleset_tech_flag(payload2, delta_cache)

    assert result2['id'] == 17  # New value
    assert result2['name'] == 'Flag2'  # New value
    assert result2['helptxt'] == 'Help1'  # From cache


@pytest.mark.unit
def test_decode_ruleset_tech_flag_empty_strings(delta_cache):
    """Test handling of empty strings."""
    # All fields present, but name and helptxt are empty
    payload = (
        b'\x07'  # All fields present
        b'\x00'  # id: 0
        b'\x00'  # Empty name
        b'\x00'  # Empty helptxt
    )

    result = decode_ruleset_tech_flag(payload, delta_cache)

    assert result['id'] == 0
    assert result['name'] == ''
    assert result['helptxt'] == ''


# ============================================================================
# PACKET_RULESET_GOVERNMENT Tests
# ============================================================================


@pytest.mark.unit
def test_decode_ruleset_government_all_fields(delta_cache):
    """Test decoding PACKET_RULESET_GOVERNMENT with all fields present (no cache)."""
    # Bitvector: 0x07ff (all 11 bits set)
    payload = (
        b'\xff\x07'  # All 11 bits set (little-endian)
        b'\x00'  # id: 0 (SINT8)
        b'\x00'  # reqs_count: 0
        # no requirements array (count is 0)
        b'Anarchy\x00'  # name
        b'Anarchy\x00'  # rule_name
        b'gov.anarchy\x00'  # graphic_str
        b'-\x00'  # graphic_alt
        b'g_anarchy\x00'  # sound_str
        b'-\x00'  # sound_alt
        b'-\x00'  # sound_alt2
        b'A chaotic form of government.\x00'  # helptext
    )

    result = protocol.decode_ruleset_government(payload, delta_cache)

    assert result['id'] == 0
    assert result['reqs_count'] == 0
    assert result['reqs'] == []
    assert result['name'] == 'Anarchy'
    assert result['rule_name'] == 'Anarchy'
    assert result['graphic_str'] == 'gov.anarchy'
    assert result['graphic_alt'] == '-'
    assert result['sound_str'] == 'g_anarchy'
    assert result['sound_alt'] == '-'
    assert result['sound_alt2'] == '-'
    assert result['helptext'] == 'A chaotic form of government.'


@pytest.mark.unit
def test_decode_ruleset_government_with_requirements(delta_cache):
    """Test government with requirements array."""
    # Bitvector: 0x07ff (all 11 bits set)
    payload = (
        b'\xff\x07'  # All bits set
        b'\x01'  # id: 1 (SINT8)
        b'\x02'  # reqs_count: 2
        # Requirement 1: 10 bytes
        b'\x03'  # type: 3
        b'\x00\x00\x00\x05'  # value: 5 (sint32, big-endian)
        b'\x02'  # range: 2
        b'\x00'  # survives: false
        b'\x01'  # present: true
        b'\x00'  # quiet: false
        # Requirement 2: 10 bytes
        b'\x04'  # type: 4
        b'\x00\x00\x00\x0a'  # value: 10 (sint32, big-endian)
        b'\x01'  # range: 1
        b'\x01'  # survives: true
        b'\x01'  # present: true
        b'\x00'  # quiet: false
        b'Republic\x00'  # name
        b'Republic\x00'  # rule_name
        b'gov.republic\x00'  # graphic_str
        b'-\x00'  # graphic_alt
        b'g_republic\x00'  # sound_str
        b'-\x00'  # sound_alt
        b'-\x00'  # sound_alt2
        b'A democratic government.\x00'  # helptext
    )

    result = protocol.decode_ruleset_government(payload, delta_cache)

    assert result['id'] == 1
    assert result['reqs_count'] == 2
    assert len(result['reqs']) == 2
    assert result['reqs'][0]['type'] == 3
    assert result['reqs'][0]['value'] == 5
    assert result['reqs'][0]['present'] is True
    assert result['reqs'][1]['type'] == 4
    assert result['reqs'][1]['value'] == 10
    assert result['name'] == 'Republic'


@pytest.mark.unit
def test_decode_ruleset_government_delta_update(delta_cache):
    """Test delta update with only some fields changing."""
    # First packet: populate cache with all fields
    payload1 = (
        b'\xff\x07'  # All bits set
        b'\x00'  # id: 0
        b'\x00'  # reqs_count: 0
        b'Anarchy\x00'
        b'Anarchy\x00'
        b'gov.anarchy\x00'
        b'-\x00'
        b'g_anarchy\x00'
        b'-\x00'
        b'-\x00'
        b'Original help.\x00'
    )
    protocol.decode_ruleset_government(payload1, delta_cache)

    # Second packet: only id and name change (bits 0, 3)
    payload2 = (
        b'\x09\x00'  # Bits 0 and 3 set (0x0009 = 0b00001001)
        b'\x01'  # id: 1
        b'Democracy\x00'  # name
    )
    result2 = protocol.decode_ruleset_government(payload2, delta_cache)

    assert result2['id'] == 1  # New value
    assert result2['name'] == 'Democracy'  # New value
    assert result2['rule_name'] == 'Anarchy'  # From cache
    assert result2['graphic_str'] == 'gov.anarchy'  # From cache
    assert result2['helptext'] == 'Original help.'  # From cache


@pytest.mark.unit
def test_decode_ruleset_government_strings_only(delta_cache):
    """Test delta update with only string fields (bits 3-10), like captured packet."""
    # First packet: set id and reqs_count
    payload1 = (
        b'\x03\x00'  # Bits 0, 1 set
        b'\x00'  # id: 0
        b'\x00'  # reqs_count: 0
    )
    protocol.decode_ruleset_government(payload1, delta_cache)

    # Second packet: update only strings (bits 3-10), like inbound_0933_type145.packet
    payload2 = (
        b'\xf8\x07'  # Bits 3-10 set (0x07f8)
        b'Anarchy\x00'  # name
        b'Anarchy\x00'  # rule_name
        b'gov.anarchy\x00'  # graphic_str
        b'-\x00'  # graphic_alt
        b'g_anarchy\x00'  # sound_str
        b'-\x00'  # sound_alt
        b'-\x00'  # sound_alt2
        b'Anarchy is simply the absence of any recognizable government.\x00'  # helptext
    )
    result2 = protocol.decode_ruleset_government(payload2, delta_cache)

    assert result2['id'] == 0  # From cache
    assert result2['reqs_count'] == 0  # From cache
    assert result2['name'] == 'Anarchy'  # New value
    assert result2['rule_name'] == 'Anarchy'  # New value
    assert result2['graphic_str'] == 'gov.anarchy'  # New value
    assert result2['helptext'].startswith('Anarchy is simply')  # New value


@pytest.mark.unit
def test_decode_ruleset_government_empty_strings(delta_cache):
    """Test handling of empty optional strings."""
    payload = (
        b'\xff\x07'  # All bits set
        b'\x02'  # id: 2
        b'\x00'  # reqs_count: 0
        b'Test Gov\x00'  # name
        b'test_gov\x00'  # rule_name
        b'\x00'  # graphic_str: empty
        b'\x00'  # graphic_alt: empty
        b'\x00'  # sound_str: empty
        b'\x00'  # sound_alt: empty
        b'\x00'  # sound_alt2: empty
        b'\x00'  # helptext: empty
    )

    result = protocol.decode_ruleset_government(payload, delta_cache)

    assert result['id'] == 2
    assert result['name'] == 'Test Gov'
    assert result['graphic_str'] == ''
    assert result['sound_str'] == ''
    assert result['helptext'] == ''
