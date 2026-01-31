"""
Unit tests for packet_specs - FreeCiv packet specification system.

Tests the declarative packet specification system that defines packet structures
for the delta protocol decoder.
"""

import pytest
from fc_client.packet_specs import FieldSpec, PacketSpec, get_packet_spec, PACKET_SPECS

# ============================================================================
# FieldSpec Tests
# ============================================================================


@pytest.mark.unit
def test_field_spec_basic_initialization():
    """FieldSpec should initialize with required fields."""
    field = FieldSpec(name="test_field", type_name="UINT32")

    assert field.name == "test_field"
    assert field.type_name == "UINT32"
    assert field.is_key is False
    assert field.is_bool is False


@pytest.mark.unit
def test_field_spec_key_field():
    """FieldSpec should support is_key flag."""
    field = FieldSpec(name="id", type_name="UINT32", is_key=True)

    assert field.is_key is True


@pytest.mark.unit
def test_field_spec_string_default_value():
    """STRING fields should default to empty string."""
    field = FieldSpec(name="message", type_name="STRING")

    assert field.default_value == ""


@pytest.mark.unit
def test_field_spec_bool_default_value():
    """BOOL fields should default to False and set is_bool=True."""
    field = FieldSpec(name="flag", type_name="BOOL")

    assert field.default_value is False
    assert field.is_bool is True


@pytest.mark.unit
def test_field_spec_sint_default_value():
    """SINT fields should default to -1."""
    field_sint16 = FieldSpec(name="value16", type_name="SINT16")
    field_sint32 = FieldSpec(name="value32", type_name="SINT32")

    assert field_sint16.default_value == -1
    assert field_sint32.default_value == -1


@pytest.mark.unit
def test_field_spec_uint_default_value():
    """UINT fields should default to 0."""
    field_uint8 = FieldSpec(name="value8", type_name="UINT8")
    field_uint32 = FieldSpec(name="value32", type_name="UINT32")

    assert field_uint8.default_value == 0
    assert field_uint32.default_value == 0


@pytest.mark.unit
def test_field_spec_custom_default_value():
    """Should allow custom default values."""
    field = FieldSpec(name="count", type_name="UINT32", default_value=42)

    assert field.default_value == 42


@pytest.mark.unit
def test_field_spec_explicit_is_bool():
    """Should respect explicitly set is_bool flag."""
    field = FieldSpec(name="flag", type_name="UINT8", is_bool=True)

    assert field.is_bool is True


# ============================================================================
# PacketSpec Tests
# ============================================================================


@pytest.mark.unit
def test_packet_spec_basic_initialization():
    """PacketSpec should initialize with required fields."""
    fields = [
        FieldSpec(name="id", type_name="UINT32", is_key=True),
        FieldSpec(name="value", type_name="SINT32"),
    ]
    spec = PacketSpec(packet_type=100, name="TEST_PACKET", has_delta=True, fields=fields)

    assert spec.packet_type == 100
    assert spec.name == "TEST_PACKET"
    assert spec.has_delta is True
    assert len(spec.fields) == 2


@pytest.mark.unit
def test_packet_spec_key_fields_property():
    """key_fields should return only fields with is_key=True."""
    fields = [
        FieldSpec(name="id", type_name="UINT32", is_key=True),
        FieldSpec(name="value", type_name="SINT32"),
        FieldSpec(name="name", type_name="STRING"),
    ]
    spec = PacketSpec(packet_type=100, name="TEST", has_delta=True, fields=fields)

    key_fields = spec.key_fields

    assert len(key_fields) == 1
    assert key_fields[0].name == "id"


@pytest.mark.unit
def test_packet_spec_non_key_fields_property():
    """non_key_fields should return only fields with is_key=False."""
    fields = [
        FieldSpec(name="id", type_name="UINT32", is_key=True),
        FieldSpec(name="value", type_name="SINT32"),
        FieldSpec(name="name", type_name="STRING"),
    ]
    spec = PacketSpec(packet_type=100, name="TEST", has_delta=True, fields=fields)

    non_key_fields = spec.non_key_fields

    assert len(non_key_fields) == 2
    assert non_key_fields[0].name == "value"
    assert non_key_fields[1].name == "name"


@pytest.mark.unit
def test_packet_spec_all_key_fields():
    """Should handle packet with all key fields."""
    fields = [
        FieldSpec(name="id1", type_name="UINT32", is_key=True),
        FieldSpec(name="id2", type_name="UINT32", is_key=True),
    ]
    spec = PacketSpec(packet_type=100, name="TEST", has_delta=False, fields=fields)

    assert len(spec.key_fields) == 2
    assert len(spec.non_key_fields) == 0


@pytest.mark.unit
def test_packet_spec_all_non_key_fields():
    """Should handle packet with all non-key fields."""
    fields = [
        FieldSpec(name="value1", type_name="SINT32"),
        FieldSpec(name="value2", type_name="SINT32"),
    ]
    spec = PacketSpec(packet_type=100, name="TEST", has_delta=True, fields=fields)

    assert len(spec.key_fields) == 0
    assert len(spec.non_key_fields) == 2


@pytest.mark.unit
def test_packet_spec_num_bitvector_bits():
    """num_bitvector_bits should equal count of non-key fields."""
    fields = [
        FieldSpec(name="id", type_name="UINT32", is_key=True),
        FieldSpec(name="f1", type_name="SINT32"),
        FieldSpec(name="f2", type_name="SINT32"),
        FieldSpec(name="f3", type_name="SINT32"),
    ]
    spec = PacketSpec(packet_type=100, name="TEST", has_delta=True, fields=fields)

    assert spec.num_bitvector_bits == 3


@pytest.mark.unit
def test_packet_spec_num_bitvector_bytes_exact():
    """num_bitvector_bytes should calculate exact bytes (no remainder)."""
    # 8 non-key fields = 8 bits = 1 byte
    fields = [FieldSpec(name=f"f{i}", type_name="SINT32") for i in range(8)]
    spec = PacketSpec(packet_type=100, name="TEST", has_delta=True, fields=fields)

    assert spec.num_bitvector_bits == 8
    assert spec.num_bitvector_bytes == 1


@pytest.mark.unit
def test_packet_spec_num_bitvector_bytes_ceiling():
    """num_bitvector_bytes should round up (ceiling division)."""
    # 9 non-key fields = 9 bits = 2 bytes (ceil(9/8) = 2)
    fields = [FieldSpec(name=f"f{i}", type_name="SINT32") for i in range(9)]
    spec = PacketSpec(packet_type=100, name="TEST", has_delta=True, fields=fields)

    assert spec.num_bitvector_bits == 9
    assert spec.num_bitvector_bytes == 2


@pytest.mark.unit
def test_packet_spec_num_bitvector_bytes_various_sizes():
    """Test bitvector byte calculation for various field counts."""
    test_cases = [
        (1, 1),  # 1 bit -> 1 byte
        (7, 1),  # 7 bits -> 1 byte
        (8, 1),  # 8 bits -> 1 byte
        (9, 2),  # 9 bits -> 2 bytes
        (15, 2),  # 15 bits -> 2 bytes
        (16, 2),  # 16 bits -> 2 bytes
        (17, 3),  # 17 bits -> 3 bytes
    ]

    for num_fields, expected_bytes in test_cases:
        fields = [FieldSpec(name=f"f{i}", type_name="SINT32") for i in range(num_fields)]
        spec = PacketSpec(packet_type=100, name="TEST", has_delta=True, fields=fields)
        assert (
            spec.num_bitvector_bytes == expected_bytes
        ), f"Expected {expected_bytes} bytes for {num_fields} fields, got {spec.num_bitvector_bytes}"


# ============================================================================
# Packet Registry Tests
# ============================================================================


@pytest.mark.unit
def test_get_packet_spec_existing_packet():
    """get_packet_spec should return spec for registered packet type."""
    # Packet type 25 (CHAT_MSG) is registered in packet_specs.py
    spec = get_packet_spec(25)

    assert spec.packet_type == 25
    assert spec.name == "PACKET_CHAT_MSG"
    assert spec.has_delta is True


@pytest.mark.unit
def test_get_packet_spec_unknown_packet():
    """get_packet_spec should raise KeyError for unknown packet type."""
    with pytest.raises(KeyError) as exc_info:
        get_packet_spec(9999)

    # Error message should be helpful
    assert "No specification found" in str(exc_info.value)
    assert "9999" in str(exc_info.value)
    assert "Available types" in str(exc_info.value)


@pytest.mark.unit
def test_packet_specs_registry_has_chat_msg():
    """PACKET_SPECS should have CHAT_MSG (25) defined."""
    assert 25 in PACKET_SPECS
    spec = PACKET_SPECS[25]
    assert spec.name == "PACKET_CHAT_MSG"
    assert len(spec.fields) == 6  # message, tile, event, turn, phase, conn_id


@pytest.mark.unit
def test_chat_msg_spec_field_names():
    """CHAT_MSG spec should have expected field names."""
    spec = PACKET_SPECS[25]
    field_names = [f.name for f in spec.fields]

    expected_names = ["message", "tile", "event", "turn", "phase", "conn_id"]
    assert field_names == expected_names


@pytest.mark.unit
def test_chat_msg_spec_field_types():
    """CHAT_MSG spec should have correct field types."""
    spec = PACKET_SPECS[25]

    # Check field types
    assert spec.fields[0].type_name == "STRING"  # message
    assert spec.fields[1].type_name == "SINT32"  # tile
    assert spec.fields[2].type_name == "SINT16"  # event
    assert spec.fields[3].type_name == "SINT16"  # turn
    assert spec.fields[4].type_name == "SINT16"  # phase
    assert spec.fields[5].type_name == "SINT16"  # conn_id


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.unit
def test_packet_spec_empty_fields():
    """Should handle packet with no fields (edge case)."""
    spec = PacketSpec(packet_type=100, name="EMPTY_PACKET", has_delta=False, fields=[])

    assert len(spec.fields) == 0
    assert len(spec.key_fields) == 0
    assert len(spec.non_key_fields) == 0
    assert spec.num_bitvector_bits == 0
    assert spec.num_bitvector_bytes == 0
