# FreeCiv Delta Protocol - Comprehensive Reference

This document provides detailed technical documentation on FreeCiv's delta protocol and bitvector implementation, based on analysis of the FreeCiv source code in `freeciv/common/`. This reference is intended to eliminate the need for repeated research when implementing or debugging delta protocol features.

## Table of Contents

1. [Delta Protocol Overview](#delta-protocol-overview)
2. [Bitvector Representation](#bitvector-representation)
3. [Cache Structure and Lifecycle](#cache-structure-and-lifecycle)
4. [Encoding and Decoding Algorithms](#encoding-and-decoding-algorithms)
5. [Array-Diff Optimization](#array-diff-optimization)
6. [Packet Specification Flags](#packet-specification-flags)
7. [Practical Implementation Examples](#practical-implementation-examples)
8. [Common Pitfalls and Edge Cases](#common-pitfalls-and-edge-cases)
9. [Testing Strategy](#testing-strategy)
10. [Related Protocol Features](#related-protocol-features)

---

## Delta Protocol Overview

### What is the Delta Protocol?

The delta protocol is FreeCiv's bandwidth optimization technique that transmits **only changed fields** in frequently-sent packets, rather than resending complete packet data every time. This is crucial for multiplayer games with hundreds of cities, units, and players where state changes frequently but only specific fields change between updates.

### Key Benefits

- **Reduces network bandwidth by 60-90%** for typical game traffic
- **Enables smoother gameplay** for players on slow connections
- **Allows servers to handle more concurrent players**
- **Reduces server CPU load** by avoiding redundant serialization

### When Delta Protocol is Used

- **Enabled by default** for most packets unless `no-delta` flag is set
- **Particularly effective** for info packets (`is-info`, `is-game-info` flags)
- **Most beneficial** for large packets with many fields (e.g., `PACKET_GAME_INFO` with 200+ fields)
- **Not used** for packets that always have different data (e.g., `PACKET_GENERIC_INTEGER`)

### Architecture Overview

Client and server maintain **synchronized caches** of the last transmitted packet values. When sending updates, only fields that differ from cached values are transmitted, with a **bitvector** indicating which fields are present.

**Basic Flow:**
```
1. Send first packet → All fields transmitted → Cache populated
2. Field values change → Compare with cache → Build bitvector
3. Send delta packet → Key fields + Bitvector + Changed fields only
4. Receiver decodes → Combines payload + cache → Complete packet
5. Update cache → Ready for next delta
```

---

## Bitvector Representation

### What is a Bitvector?

A bitvector is a **compact bit array** where each bit represents the presence (1) or absence (0) of one non-key field in the packet payload. Bitvectors enable efficient field-level delta encoding.

### Memory Layout (Little-Endian)

**Critical:** FreeCiv uses **little-endian bit ordering within each byte**.

```
Byte 0: bits 0-7   (bit 0 = LSB = 0x01, bit 7 = MSB = 0x80)
Byte 1: bits 8-15  (bit 8 = LSB = 0x01, bit 15 = MSB = 0x80)
Byte 2: bits 16-23
...

Example: Packet with 10 non-key fields
- Bitvector size: ceil(10 / 8) = 2 bytes
- Fields present: 0, 2, 4, 9
- Binary: Byte 0 = 0b00010101, Byte 1 = 0b00000010
- Hex: [0x15, 0x02]
```

### Bit Mapping

```
Field Index → Bit Position
  0         → Byte 0, bit 0 (mask: 0x01)
  1         → Byte 0, bit 1 (mask: 0x02)
  2         → Byte 0, bit 2 (mask: 0x04)
  7         → Byte 0, bit 7 (mask: 0x80)
  8         → Byte 1, bit 0 (mask: 0x01)
  15        → Byte 1, bit 7 (mask: 0x80)
  16        → Byte 2, bit 0 (mask: 0x01)
```

### Size Calculation

```python
num_bytes = (num_non_key_fields + 7) // 8  # Ceiling division

# Examples:
# 1-8 fields   → 1 byte
# 9-16 fields  → 2 bytes
# 17-24 fields → 3 bytes
# 25 fields    → 4 bytes
```

### Python Implementation

```python
def read_bitvector(data: bytes, offset: int, num_bits: int) -> Tuple[int, int]:
    """
    Read bitvector from byte array and return as integer.

    Args:
        data: Packet payload bytes
        offset: Starting position in data
        num_bits: Number of bits in bitvector

    Returns:
        Tuple of (bitvector_value, new_offset)
    """
    num_bytes = (num_bits + 7) // 8  # Ceiling division
    bitvector_bytes = data[offset:offset + num_bytes]

    # CRITICAL: Use 'little' endian to match FreeCiv's LSB-first byte ordering
    bitvector = int.from_bytes(bitvector_bytes, byteorder='little')

    return bitvector, offset + num_bytes


def is_bit_set(bitvector: int, bit_index: int) -> bool:
    """
    Check if bit at given index is set.

    Args:
        bitvector: Integer representation of bitvector
        bit_index: Zero-based bit position

    Returns:
        True if bit is set, False otherwise
    """
    return (bitvector & (1 << bit_index)) != 0


def set_bit(bitvector: int, bit_index: int) -> int:
    """Set bit at given index."""
    return bitvector | (1 << bit_index)


def clear_bit(bitvector: int, bit_index: int) -> int:
    """Clear bit at given index."""
    return bitvector & ~(1 << bit_index)
```

### C Implementation Reference (FreeCiv Source)

**File:** `freeciv/utility/bitvector.h`

```c
// Calculate number of bytes needed for N bits
#define _BV_BYTES(bits)        ((((bits) - 1) / 8) + 1)

// Get byte index for a bit number
#define _BV_BYTE_INDEX(bits)   ((bits) / 8)

// Get bitmask for a bit within its byte
#define _BV_BITMASK(bit)       (1u << ((bit) & 0x7))

// Check if bit is set
#define BV_ISSET(bv, bit) \
    ((bv).vec[_BV_BYTE_INDEX(bit)] & _BV_BITMASK(bit)) != 0

// Set a bit
#define BV_SET(bv, bit) \
    (bv).vec[_BV_BYTE_INDEX(bit)] |= _BV_BITMASK(bit)

// Clear a bit
#define BV_CLR(bv, bit) \
    (bv).vec[_BV_BYTE_INDEX(bit)] &= ~_BV_BITMASK(bit)
```

---

## Cache Structure and Lifecycle

### Cache Data Structure

```python
class DeltaCache:
    """
    Cache for delta protocol packet values.

    Structure: {packet_type: {key_tuple: {field_name: field_value}}}
    """
    _cache: Dict[int, Dict[Tuple, Dict[str, Any]]]
```

### Cache Key Format

- **packet_type**: Integer packet type number (e.g., 25 for `PACKET_CHAT_MSG`)
- **key_tuple**: Tuple of key field values for cache lookup
  - Packets **without** key fields: empty tuple `()`
  - Packets with **one** key field: single-element tuple `(value,)`
  - Packets with **multiple** key fields: multi-element tuple `(key1, key2, ...)`

### Example Cache State

```python
{
    31: {  # PACKET_CITY_INFO (has key field: city id)
        (42,): {  # City with id=42
            'tile': 1234,
            'owner': 2,
            'size': 5,
            'production': 'Warriors',
            'food_stock': 8,
            'shield_stock': 12,
            # ... 100+ other fields
        },
        (43,): {  # City with id=43
            'tile': 5678,
            'owner': 2,
            'size': 3,
            'production': 'Settler',
            'food_stock': 5,
            'shield_stock': 0,
        }
    },
    25: {  # PACKET_CHAT_MSG (no key fields)
        (): {  # Empty tuple for packets without keys
            'message': 'Last chat message',
            'tile': -1,
            'event': 0,
            'turn': 42,
            'phase': 0,
            'conn_id': 1,
        }
    }
}
```

### Cache Lifecycle

| Phase | Action | Description |
|-------|--------|-------------|
| **Initialization** | Cache starts empty | When client connects to server |
| **First Packet** | All fields transmitted | Cache populated with initial values |
| **Subsequent Packets** | Only changed fields transmitted | Cache updated with new values |
| **Cache Miss** | Use default values | If no cached entry exists, use field defaults |
| **Disconnect** | Entire cache cleared | Ensures clean state for next connection |

### Cache Operations

```python
# Retrieve cached packet
cached = delta_cache.get_cached_packet(packet_type, key_tuple)
# Returns: Dict[str, Any] or None if not found

# Update cache after decoding
delta_cache.update_cache(packet_type, key_tuple, complete_fields_dict)

# Clear all cache (on disconnect)
delta_cache.clear_all()

# Clear specific packet type
delta_cache.clear_packet_type(packet_type)
```

### Memory Considerations

- Cache grows with number of game entities (cities, units, players, etc.)
- **Typical game:** 50-200 cities × ~150 fields = ~100KB cached data
- **Large games:** 500+ cities can use 1-2MB of cache
- Cache is **per-connection**, server maintains separate cache per client

---

## Encoding and Decoding Algorithms

### Decoding Algorithm (Client Receives Packet)

```python
def decode_delta_packet(
    payload: bytes,
    packet_spec: PacketSpec,
    delta_cache: DeltaCache
) -> Dict[str, Any]:
    """
    Decode delta-encoded packet from network stream.

    Steps:
    1. Read all key fields (always present)
    2. Read bitvector (if packet has non-key fields)
    3. Retrieve cached packet (or use defaults)
    4. For each non-key field:
       - If BOOL: use bitvector bit value directly (header folding)
       - Elif bit set: read new value from payload
       - Else: use cached value
    5. Update cache with complete packet
    6. Return complete field dictionary

    Args:
        payload: Raw packet body bytes (after header removed)
        packet_spec: PacketSpec defining packet structure
        delta_cache: DeltaCache instance for caching

    Returns:
        Dictionary mapping field names to values
    """
    offset = 0
    fields = {}

    # Step 1: Read key fields (always transmitted, never in bitvector)
    key_values = []
    for field_spec in packet_spec.key_fields:
        value, offset = decode_field(payload, offset, field_spec)
        fields[field_spec.name] = value
        key_values.append(value)

    key_tuple = tuple(key_values)

    # Step 2: Read bitvector (one bit per non-key field)
    if packet_spec.num_bitvector_bits > 0:
        bitvector, offset = read_bitvector(
            payload, offset, packet_spec.num_bitvector_bits
        )
    else:
        # Packet with only key fields has no bitvector
        bitvector = 0

    # Step 3: Get cached packet values
    cached = delta_cache.get_cached_packet(packet_spec.packet_type, key_tuple)
    if cached is None:
        # First time seeing this packet instance - use default values
        cached = {
            field.name: field.default_value
            for field in packet_spec.non_key_fields
        }

    # Step 4: Read non-key fields based on bitvector
    for bit_index, field_spec in enumerate(packet_spec.non_key_fields):
        if field_spec.is_bool:
            # BOOL header folding: bitvector bit IS the field value
            # No additional payload bytes consumed
            fields[field_spec.name] = is_bit_set(bitvector, bit_index)
        elif is_bit_set(bitvector, bit_index):
            # Field changed - read new value from payload
            value, offset = decode_field(payload, offset, field_spec)
            fields[field_spec.name] = value
        else:
            # Field unchanged - use cached value
            fields[field_spec.name] = cached[field_spec.name]

    # Step 5: Update cache with complete packet
    delta_cache.update_cache(packet_spec.packet_type, key_tuple, fields)

    return fields
```

### Encoding Algorithm (Client Sends Packet)

```python
def encode_delta_packet(
    fields: Dict[str, Any],
    packet_spec: PacketSpec,
    delta_cache: DeltaCache
) -> bytes:
    """
    Encode packet with delta compression.

    Steps:
    1. Extract key field values
    2. Retrieve cached packet
    3. Build bitvector comparing new vs cached values
    4. Encode key fields (always)
    5. Encode bitvector
    6. Encode changed non-key fields (skip BOOLs)
    7. Update cache

    Args:
        fields: Dictionary of field names to values
        packet_spec: PacketSpec defining packet structure
        delta_cache: DeltaCache instance for caching

    Returns:
        Encoded packet body bytes (without packet header)
    """
    payload = b''
    key_values = []

    # Step 1 & 4: Encode key fields (always transmitted)
    for field_spec in packet_spec.key_fields:
        value = fields[field_spec.name]
        key_values.append(value)
        payload += encode_field(value, field_spec)

    key_tuple = tuple(key_values)

    # Step 2: Get cached packet
    cached = delta_cache.get_cached_packet(packet_spec.packet_type, key_tuple)

    # Step 3: Build bitvector by comparing new vs cached values
    bitvector = 0
    for bit_index, field_spec in enumerate(packet_spec.non_key_fields):
        new_value = fields[field_spec.name]

        # Set bit if field changed OR first transmission
        if cached is None or cached[field_spec.name] != new_value:
            bitvector |= (1 << bit_index)

    # Step 5: Encode bitvector
    num_bytes = (packet_spec.num_bitvector_bits + 7) // 8
    payload += bitvector.to_bytes(num_bytes, byteorder='little')

    # Step 6: Encode changed non-key fields
    for bit_index, field_spec in enumerate(packet_spec.non_key_fields):
        if field_spec.is_bool:
            # BOOL: value already encoded in bitvector, no payload byte
            continue
        elif is_bit_set(bitvector, bit_index):
            # Changed field: encode it to payload
            value = fields[field_spec.name]
            payload += encode_field(value, field_spec)

    # Step 7: Update cache
    delta_cache.update_cache(packet_spec.packet_type, key_tuple, fields)

    return payload
```

### Boolean Header Folding Optimization

**Concept:** For BOOL fields, the bitvector bit IS the field value. No additional payload bytes are consumed.

```python
# Without header folding (wasteful):
# - Bitvector bit = "is field present?"
# - Payload byte = actual boolean value (0 or 1)
# - Total: 1 bit + 1 byte per BOOL

# With header folding (efficient):
# - Bitvector bit = actual boolean value
# - No payload byte needed
# - Total: 1 bit per BOOL (8x compression!)
```

**Implementation:**
```python
# Decoding BOOL field
if field_spec.is_bool:
    # Read value directly from bitvector
    value = is_bit_set(bitvector, bit_index)
    # offset unchanged - no payload bytes consumed

# Encoding BOOL field
if field_spec.is_bool:
    # Set bitvector bit to field value
    if fields[field_spec.name]:
        bitvector |= (1 << bit_index)
    # No payload bytes written
```

---

## Array-Diff Optimization

**⚠️ IMPORTANT: Array-diff is independent of delta protocol! ⚠️**

Array-diff is a separate optimization that works **within** both delta and non-delta packets. It transmits only changed array elements instead of the entire array.

### What is Array-Diff?

Array-diff is an optimization for array fields that transmits only the changed elements as index-value pairs, followed by a sentinel value indicating the end of changes.

### When Array-Diff is Used

Array-diff is enabled on specific array fields marked with the `(diff)` flag in packets.def:

```c
// Example from PACKET_RULESET_GAME
veteran_name[veteran_levels](diff)
               ^^^^^^^^^^^^^^^
               This field uses array-diff encoding
```

### Array-Diff Format

```
[index₀] [value₀] [index₁] [value₁] ... [array_size_sentinel]
```

**Components:**
- **index**: uint8 (0-254), the array index being updated
- **value**: The new value for that array element (type varies)
- **sentinel**: uint8 equal to the array size (signals end of changes)

### Encoding Rules

1. **Index is uint8**: Maximum array size is 255 elements
2. **Only changed elements transmitted**: Compared to cached array values
3. **Sentinel value = array size**: For array of size 10, sentinel is 10
4. **Protocol error if index > array_size**: Invalid packet, must reject
5. **Works with delta protocol**: Array-diff can be within delta-encoded fields

### Decoding Algorithm

```python
def decode_array_diff(payload, offset, array_size, element_decoder, cached_array=None):
    """Decode array-diff encoded field.

    Args:
        payload: Raw packet bytes
        offset: Current read position in payload
        array_size: Fixed size of the array (from packet spec)
        element_decoder: Function to decode single element from bytes
                        Signature: decoder(payload, offset) -> (value, new_offset)
        cached_array: Previously received array values (for delta protocol)
                     If None, creates empty array

    Returns:
        (decoded_array, new_offset)

    Raises:
        ValueError: If index > array_size (protocol error)
    """
    # Start with cached values or create empty array
    if cached_array is not None:
        result = list(cached_array)  # Copy cached values
    else:
        result = [None] * array_size  # Empty array

    # Read index-value pairs until sentinel
    while True:
        # Read index (uint8)
        index = payload[offset]
        offset += 1

        # Check for sentinel (end marker)
        if index == array_size:
            break  # Done reading changes

        # Validate index
        if index > array_size:
            raise ValueError(f"Invalid array-diff index {index} > array_size {array_size}")

        # Read value at this index
        value, offset = element_decoder(payload, offset)
        result[index] = value

    return result, offset
```

### Encoding Algorithm

```python
def encode_array_diff(array, cached_array, array_size, element_encoder):
    """Encode array using array-diff format.

    Args:
        array: Current array values
        cached_array: Previously sent array values (or None for first send)
        array_size: Size of the array
        element_encoder: Function to encode single element to bytes
                        Signature: encoder(value) -> bytes

    Returns:
        bytes: Encoded array-diff data
    """
    output = bytearray()

    # Find changed elements
    for index in range(array_size):
        current = array[index]
        cached = cached_array[index] if cached_array else None

        # Check if element changed
        if current != cached:
            # Write index (uint8)
            output.append(index)

            # Write value
            output.extend(element_encoder(current))

    # Write sentinel (array_size)
    output.append(array_size)

    return bytes(output)
```

### Practical Example

**Packet Specification:**
```c
// PACKET_RULESET_GAME (141)
UINT8 veteran_levels;
STRING veteran_name[veteran_levels](diff);
```

**Scenario:** Sending veteran names for 4 levels

**First transmission (no cache):**
```
Payload: [0]["green"][1]["veteran"][2]["hardened"][3]["elite"][4]
         ^ index   ^value    ^ index   ^value      ...         ^sentinel
```

**Breakdown:**
- `[0]` = index 0 (uint8 = 0x00)
- `["green"]` = null-terminated string "green\0"
- `[1]` = index 1 (uint8 = 0x01)
- `["veteran"]` = null-terminated string "veteran\0"
- `[2]` = index 2 (uint8 = 0x02)
- `["hardened"]` = null-terminated string "hardened\0"
- `[3]` = index 3 (uint8 = 0x03)
- `["elite"]` = null-terminated string "elite\0"
- `[4]` = sentinel (uint8 = 0x04, equals array_size)

**Second transmission (only element 2 changed):**
```
Payload: [2]["seasoned"][4]
         ^ index  ^new value ^sentinel
```

Only the changed element is transmitted. Cache is updated for element 2, other elements remain unchanged.

### Interaction with Delta Protocol

Array-diff works **within** delta protocol fields:

```
Delta Packet Structure:
[bitvector] [key_fields] [non_key_field_0] [array_diff_field] [non_key_field_2] ...
                                            ^^^^^^^^^^^^^^^^^
                                            This field uses array-diff encoding
```

**Decoding flow:**
1. Read bitvector to determine which non-key fields are present
2. Read key fields (always present)
3. For each non-key field with bit set in bitvector:
   - If field is array with `(diff)` flag: Use `decode_array_diff()`
   - Else: Use standard field decoder

### Implementation Requirements

**For Packet Handler Implementers:**

1. **Identify diff arrays**: Check packets.def for `(diff)` flag on array fields
2. **Choose correct decoder**: Use `decode_array_diff()` for diff arrays, standard decoder otherwise
3. **Provide array size**: Must know array size (from preceding field or packet spec)
4. **Pass cached array**: For delta packets, pass cached array to preserve unchanged elements
5. **Handle sentinel correctly**: Sentinel value equals array_size, NOT max valid index

**Testing:**
```python
def test_array_diff_veteran_names():
    # Captured from real FreeCiv server packet
    # PACKET_RULESET_GAME veteran_name field
    payload = bytes.fromhex(
        "00 67 72 65 65 6e 00"      # [0]["green\0"]
        "01 76 65 74 65 72 61 6e 00" # [1]["veteran\0"]
        "02 68 61 72 64 65 6e 65 64 00" # [2]["hardened\0"]
        "03 65 6c 69 74 65 00"      # [3]["elite\0"]
        "04"                        # [4] = sentinel
    )

    offset = 0
    array_size = 4  # From veteran_levels field

    result, new_offset = decode_array_diff(
        payload, offset, array_size,
        element_decoder=decode_null_terminated_string,
        cached_array=None  # First transmission
    )

    assert result == ["green", "veteran", "hardened", "elite"]
    assert new_offset == len(payload)
    assert payload[new_offset - 1] == 4  # Verify sentinel
```

### Common Mistakes

❌ **Wrong: Treating sentinel as max index**
```python
# WRONG: sentinel is array_size, not max_index
if index >= array_size:  # Off-by-one error
    break
```

✅ **Correct: Sentinel equals array_size**
```python
# CORRECT: sentinel is array_size exactly
if index == array_size:
    break
elif index > array_size:
    raise ValueError("Invalid index")
```

❌ **Wrong: Using array-diff for all arrays**
```python
# WRONG: Not all arrays use diff encoding
for field in packet_spec.fields:
    if field.is_array:
        decode_array_diff(...)  # May be wrong!
```

✅ **Correct: Check for diff flag**
```python
# CORRECT: Only use array-diff if marked with (diff)
for field in packet_spec.fields:
    if field.is_array and field.has_diff_flag:
        decode_array_diff(...)
    elif field.is_array:
        decode_standard_array(...)
```

### Implementation References

- **Encoding logic**: `freeciv/common/generate_packets.py:1273-1351`
- **Decoding logic**: `freeciv/common/generate_packets.py:1390-1441`
- **Documentation**: `freeciv/doc/README.delta` lines 23-29
- **Generated C code**: Search for `DIO_BV_GET` and `DIO_BV_PUT` in `packets_gen.c`

### Current Status in Our Client

- ❌ **Not implemented** - Our client does not support array-diff yet
- 🔍 **Required for**: PACKET_RULESET_GAME (141) and ~50+ other packets with diff arrays
- 📝 **Next steps**: Implement generic array-diff decoder in `fc_client/protocol.py`

---

## Packet Specification Flags

### Packet-Level Flags

**Format:** `PACKET_<NAME> = <num>; <flags>`

#### `no-delta`

**Disable delta protocol for this packet.** All fields always transmitted.

**When to use:**
- Packet data always changes (e.g., `PACKET_GENERIC_INTEGER`)
- Packet sent only once (e.g., `PACKET_SERVER_JOIN_REQ`)
- Bandwidth savings would be minimal
- Need deterministic packet size

**Example:**
```c
PACKET_SERVER_JOIN_REQ = 4; cs, dsend, no-delta, no-handle
PACKET_SERVER_JOIN_REPLY = 5; sc, no-delta, post-send, post-recv
PACKET_ENDGAME_REPORT = 12; sc, lsend, no-delta
```

**Note:** Disables use of 0 as default field value. All fields must have explicit values.

#### `is-info`

**Enable aggressive caching.** Duplicate packets with identical content can be discarded.

**When to use:**
- Packets that represent current state (not events)
- Safe if client cannot modify state independently
- Server frequently sends same values

**Warning:** Dangerous if client can modify state (would desync from server).

**Example:**
```c
PACKET_GAME_INFO = 16; sc, is-info
PACKET_PLAYER_INFO = 51; sc, is-info
```

#### `is-game-info`

**Like `is-info` but cache reset when connection changes player target.**

**When to use:**
- Player-specific state information
- Per-player cities, units, research, etc.

**Example:**
```c
PACKET_TILE_INFO = 15; sc, lsend, is-game-info
PACKET_CITY_INFO = 31; sc, lsend, is-game-info, force
PACKET_UNIT_INFO = 63; sc, lsend, is-game-info
```

#### `force`

**Add `force_to_send` parameter to sending functions.**

When true, ignores `is-info` caching and sends even if content unchanged.

**Example:**
```c
PACKET_CITY_INFO = 31; sc, lsend, is-game-info, force
```

**Usage:**
```c
// Normal send - skipped if content unchanged
send_packet_city_info(conn, &packet);

// Force send - always transmitted
send_packet_city_info(conn, &packet, /*force_to_send=*/TRUE);
```

#### `cancel(PACKET_FOO)`

**Cancel previously sent packet with same key.**

Used for "this entity no longer exists" packets.

**Example:**
```c
PACKET_CITY_INFO = 31; sc, lsend, is-game-info, force, cancel(PACKET_CITY_SHORT_INFO)
PACKET_CITY_REMOVE = 32; sc, dsend, cancel(PACKET_CITY_INFO, PACKET_CITY_SHORT_INFO)
```

#### Direction Flags

- **`cs`**: Client-to-server packet
- **`sc`**: Server-to-client packet

#### Send Function Flags

- **`dsend`**: Generate direct-send function taking fields as parameters
- **`lsend`**: Generate list-send function for broadcasting to multiple connections

#### Handler Flags

- **`no-handle`**: Don't generate handler prototype
- **`handle-via-fields`**: Call handler with field values as parameters
- **`handle-per-conn`**: Handler receives connection instead of player

#### Hook Flags

- **`pre-send`**: Generate `pre_send_packet_*()` hook
- **`post-send`**: Generate `post_send_packet_*()` hook
- **`post-recv`**: Generate `post_receive_packet_*()` hook

---

### Field-Level Flags

**Format:** `<TYPE> <field_name>; <flags>`

#### `key`

**This field is a key field for cache indexing.**

**Properties:**
- Always transmitted (never in bitvector)
- Used for cache lookup
- Multiple key fields create composite keys
- Order matters for cache tuple construction

**Example:**
```c
PACKET_CITY_INFO = 31; sc, lsend, is-game-info, force
  CITY id; key        // Key field - always sent
  TILE tile;          // Non-key - delta encoded
  PLAYER owner;       // Non-key - delta encoded
  CITIZENS size;      // Non-key - delta encoded
end
```

**Cache lookup:** `(packet_type=31, key_tuple=(id_value,))`

#### `diff`

**Enable array-diff optimization for array fields.**

Instead of transmitting entire array when one element changes, array-diff sends: `[index, value, index, value, ..., sentinel]` where sentinel is array size.

**Benefit:** For 200-element array with 2 changes:
- Without diff: 200 × element_size bytes
- With diff: 2 × (index_size + element_size) + index_size bytes
- Example: 200 bytes → 8 bytes (96% reduction!)

**Example:**
```c
PACKET_GAME_INFO = 16; sc, is-info
  BOOL global_advances[A_LAST]; diff    // ~200 tech discoveries
  PLAYER great_wonder_owners[B_LAST]; diff  // ~40 wonders
end
```

**Note:** Not yet implemented in this client.

#### `add-cap(capability_name)`

**Only transmit field if capability is present at runtime.**

Used for protocol versioning. Add new fields without breaking old clients.

**Example:**
```c
UINT16 anarchy; add-cap(hap2clnt)
UINT32 tech_upkeep_32; add-cap(tu32)
```

#### `remove-cap(capability_name)`

**Don't transmit field if capability is present.**

Used when removing deprecated fields. Old clients still receive field, new clients don't.

**Example:**
```c
UINT16 tech_upkeep_16; remove-cap(tu32)  // Old field
UINT32 tech_upkeep_32; add-cap(tu32)     // New replacement field
```

---

## Practical Implementation Examples

### Example 1: Simple Packet (No Key Fields)

**Packet:** `PACKET_CHAT_MSG` (packet type 25)

**Specification:**
```python
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
```

**First Transmission (All Fields):**
```python
# Cache is empty - all fields must be sent
payload1 = (
    b'\x3f' +  # Bitvector: 0b00111111 (all 6 bits set)
    encode_string("Welcome to the game!") +
    encode_sint32(-1) +     # tile (no specific tile)
    encode_sint16(0) +      # event
    encode_sint16(1) +      # turn
    encode_sint16(0) +      # phase
    encode_sint16(1)        # conn_id
)

result1 = decode_delta_packet(payload1, PACKET_SPECS[25], cache)
# result1 = {
#     'message': 'Welcome to the game!',
#     'tile': -1,
#     'event': 0,
#     'turn': 1,
#     'phase': 0,
#     'conn_id': 1
# }
# Cache now populated with these values
```

**Second Transmission (Only Message Changed):**
```python
# Cache has previous values - only send changed field
payload2 = (
    b'\x01' +  # Bitvector: 0b00000001 (only bit 0 set = message)
    encode_string("Good luck!")
    # Other fields omitted - use cached values
)

result2 = decode_delta_packet(payload2, PACKET_SPECS[25], cache)
# result2 = {
#     'message': 'Good luck!',  # From payload
#     'tile': -1,               # From cache
#     'event': 0,               # From cache
#     'turn': 1,                # From cache
#     'phase': 0,               # From cache
#     'conn_id': 1              # From cache
# }
```

**Bandwidth Savings:**
- First packet: 1 + 22 + 4 + 2 + 2 + 2 + 2 = **35 bytes**
- Second packet: 1 + 12 = **13 bytes** (63% reduction)

---

### Example 2: Packet with Key Field

**Packet:** `PACKET_CITY_INFO` (packet type 31)

**Specification (Simplified):**
```python
PACKET_SPECS[31] = PacketSpec(
    packet_type=31,
    name="PACKET_CITY_INFO",
    has_delta=True,
    fields=[
        FieldSpec(name='id', type_name='UINT32', is_key=True),
        FieldSpec(name='tile', type_name='SINT32'),
        FieldSpec(name='owner', type_name='UINT8'),
        FieldSpec(name='size', type_name='UINT8'),
        FieldSpec(name='production', type_name='STRING'),
    ]
)
```

**City 42 - Initial State:**
```python
payload1 = (
    encode_uint32(42) +         # id (key field - always present)
    b'\x0f' +                   # Bitvector: 0b00001111 (all 4 non-key fields)
    encode_sint32(1234) +       # tile
    encode_uint8(2) +           # owner (player 2)
    encode_uint8(5) +           # size
    encode_string("Warriors")   # production
)

result1 = decode_delta_packet(payload1, PACKET_SPECS[31], cache)
# Cache key: (31, (42,))
# Cache value: {'tile': 1234, 'owner': 2, 'size': 5, 'production': 'Warriors'}
```

**City 42 - Size Changed:**
```python
payload2 = (
    encode_uint32(42) +         # id (key field - always present)
    b'\x04' +                   # Bitvector: 0b00000100 (only bit 2 = size)
    encode_uint8(6)             # new size
    # tile, owner, production from cache
)

result2 = decode_delta_packet(payload2, PACKET_SPECS[31], cache)
# result2 = {'id': 42, 'tile': 1234, 'owner': 2, 'size': 6, 'production': 'Warriors'}
```

**City 43 - Initial State (Different Cache Entry):**
```python
payload3 = (
    encode_uint32(43) +         # Different id = different cache key
    b'\x0f' +
    encode_sint32(5678) +
    encode_uint8(2) +
    encode_uint8(3) +
    encode_string("Settler")
)

result3 = decode_delta_packet(payload3, PACKET_SPECS[31], cache)
# Cache now has TWO entries:
# - (31, (42,)): {'tile': 1234, 'owner': 2, 'size': 6, 'production': 'Warriors'}
# - (31, (43,)): {'tile': 5678, 'owner': 2, 'size': 3, 'production': 'Settler'}
```

---

### Example 3: Boolean Header Folding

**Packet with BOOL Fields:**
```python
PACKET_SPECS[104] = PacketSpec(
    packet_type=104,
    name="TEST_PACKET",
    has_delta=True,
    fields=[
        FieldSpec(name='id', type_name='UINT32', is_key=True),
        FieldSpec(name='is_active', type_name='BOOL'),
        FieldSpec(name='is_visible', type_name='BOOL'),
        FieldSpec(name='count', type_name='SINT16'),
    ]
)
```

**Payload with Boolean Values:**
```python
# Fields: is_active=True, is_visible=False, count=10
payload = (
    encode_uint32(1) +          # id
    b'\x05' +                   # Bitvector: 0b00000101
                                # bit 0 (is_active) = 1 → True
                                # bit 1 (is_visible) = 0 → False
                                # bit 2 (count) = 1 → present in payload
    encode_sint16(10)           # count value
    # NOTE: NO bytes for is_active or is_visible!
)

result = decode_delta_packet(payload, PACKET_SPECS[104], cache)
# result = {
#     'id': 1,
#     'is_active': True,     # From bitvector bit 0
#     'is_visible': False,   # From bitvector bit 1
#     'count': 10            # From payload
# }
```

**Bandwidth Savings:**
- Without header folding: 4 + 1 + 1 + 1 + 2 = **9 bytes**
- With header folding: 4 + 1 + 2 = **7 bytes** (22% reduction)
- For packets with many BOOLs, savings can be 50%+

---

### Example 4: Multi-Byte Bitvector

**Packet with 18 Non-Key Fields:**
```python
PACKET_SPECS[105] = PacketSpec(
    packet_type=105,
    name="LARGE_PACKET",
    has_delta=True,
    fields=[
        FieldSpec(name='id', type_name='UINT32', is_key=True),
        # 18 non-key fields (requires 3-byte bitvector)
        FieldSpec(name='f0', type_name='SINT16'),
        FieldSpec(name='f1', type_name='SINT16'),
        # ... (fields f2-f16)
        FieldSpec(name='f17', type_name='SINT16'),
    ]
)
```

**Only Fields 0, 8, 17 Changed:**
```python
# Bitvector: bits 0, 8, 17 set
# - Byte 0: 0b00000001 = 0x01 (bit 0)
# - Byte 1: 0b00000001 = 0x01 (bit 8)
# - Byte 2: 0b00000010 = 0x02 (bit 17)

payload = (
    encode_uint32(1) +          # id
    b'\x01\x01\x02' +           # 3-byte bitvector (little-endian)
    encode_sint16(100) +        # f0
    encode_sint16(800) +        # f8
    encode_sint16(1700)         # f17
)

result = decode_delta_packet(payload, PACKET_SPECS[105], cache)
# result['f0'] == 100   (from payload)
# result['f1'] == <cached>
# result['f8'] == 800   (from payload)
# result['f17'] == 1700 (from payload)
# All other fields from cache
```

---

## Common Pitfalls and Edge Cases

### Pitfall 1: Wrong Bitvector Byte Order

**Problem:** Using big-endian instead of little-endian.

```python
# ❌ WRONG: Using big-endian
bitvector = int.from_bytes(bitvector_bytes, byteorder='big')

# ✅ CORRECT: Using little-endian
bitvector = int.from_bytes(bitvector_bytes, byteorder='little')
```

**Why:** FreeCiv stores bits 0-7 in byte 0, bits 8-15 in byte 1, etc. This matches little-endian integer interpretation.

**Symptom:** Fields incorrectly marked as present/absent. Decoder reads wrong fields from payload.

---

### Pitfall 2: Forgetting Boolean Header Folding

**Problem:** Reading payload bytes for BOOL fields.

```python
# ❌ WRONG: Reading byte for BOOL field
if is_bit_set(bitvector, bit_index):
    value, offset = decode_bool(payload, offset)
    fields[field_spec.name] = value

# ✅ CORRECT: Use bitvector bit directly for BOOLs
if field_spec.is_bool:
    fields[field_spec.name] = is_bit_set(bitvector, bit_index)
else:
    if is_bit_set(bitvector, bit_index):
        value, offset = decode_field(payload, offset, field_spec)
        fields[field_spec.name] = value
```

**Symptom:** Decoder reads extra bytes, becomes desynchronized. Subsequent fields decoded from wrong offsets.

---

### Pitfall 3: Including Key Fields in Bitvector

**Problem:** Counting key fields when calculating bitvector size.

```python
# ❌ WRONG: Counting ALL fields
num_bits = len(packet_spec.fields)

# ✅ CORRECT: Only count non-key fields
num_bits = len(packet_spec.non_key_fields)
```

**Why:** Key fields are always transmitted BEFORE the bitvector. They don't get bits in the bitvector.

**Symptom:** Bitvector size mismatch. Decoder reads wrong number of bytes for bitvector.

---

### Pitfall 4: Not Handling Cache Misses

**Problem:** Assuming cached values always exist.

```python
# ❌ WRONG: Assuming cache exists
cached = delta_cache.get_cached_packet(packet_type, key_tuple)
value = cached[field_name]  # Crashes if cached is None!

# ✅ CORRECT: Handle missing cache with defaults
cached = delta_cache.get_cached_packet(packet_type, key_tuple)
if cached is None:
    cached = {
        field.name: field.default_value
        for field in packet_spec.non_key_fields
    }
value = cached[field_name]
```

**Symptom:** `AttributeError` or `KeyError` when decoding first packet with given key.

---

### Pitfall 5: Mutable Cache Values

**Problem:** Storing reference to mutable dict in cache.

```python
# ❌ WRONG: Storing reference
delta_cache._cache[packet_type][key_tuple] = fields

# Later modification affects cache:
fields['some_field'] = new_value  # Oops, cache changed unintentionally!

# ✅ CORRECT: Store a copy
delta_cache._cache[packet_type][key_tuple] = fields.copy()
```

**Symptom:** Cache contains incorrect values. Delta encoding breaks because cached values unexpectedly changed.

---

### Edge Case 1: Empty Bitvector (Only Key Fields)

**Scenario:** Packet with only key fields, no non-key fields.

```python
# Packet with zero non-key fields
if packet_spec.num_bitvector_bits == 0:
    # Don't read bitvector at all
    bitvector = 0
    # All work is done - no non-key fields to decode
else:
    bitvector, offset = read_bitvector(payload, offset, num_bits)
```

---

### Edge Case 2: First Packet with Partial Fields

**Scenario:** Server sends first packet with some fields omitted (relying on defaults).

```python
# First packet: bitvector has some bits clear
# Must use default values from FieldSpec, not None or empty

cached = delta_cache.get_cached_packet(packet_type, key_tuple)
if cached is None:
    # Initialize with defaults, NOT empty dict or None
    cached = {
        field.name: field.default_value
        for field in packet_spec.non_key_fields
    }
```

**Default values by type:**
- Integers: `0`
- Strings: `""`
- Booleans: `False`
- Arrays: Empty array `[]`

---

### Edge Case 3: Bitvector All Zeros

**Scenario:** Valid delta packet with all fields unchanged.

```python
# Packet: key fields + bitvector of all zeros
payload = encode_uint32(42) + b'\x00'

# This is VALID! Means "all fields from cache"
result = decode_delta_packet(payload, spec, cache)
# result contains id=42 plus all fields from cache
```

---

### Edge Case 4: Cache Key Collision Prevention

**Scenario:** Different packet types might use same integer key values.

```python
# City 42 and Unit 42 must have separate cache entries
# Cache key includes BOTH packet type AND key values

# City 42: cache key = (31, (42,))
# Unit 42: cache key = (63, (42,))

# These don't collide - different packet types
```

---

## Testing Strategy

### Unit Tests for Bitvector Operations

```python
def test_bitvector_little_endian():
    """Verify little-endian byte order."""
    # Bits 0, 8, 16 set
    bitvector_bytes = b'\x01\x01\x01'
    bitvector = int.from_bytes(bitvector_bytes, byteorder='little')

    assert is_bit_set(bitvector, 0)   # Byte 0, bit 0
    assert is_bit_set(bitvector, 8)   # Byte 1, bit 0
    assert is_bit_set(bitvector, 16)  # Byte 2, bit 0
    assert not is_bit_set(bitvector, 1)
    assert not is_bit_set(bitvector, 7)


def test_bitvector_size_calculation():
    """Test bitvector size at byte boundaries."""
    assert (8 + 7) // 8 == 1   # 8 fields = 1 byte
    assert (9 + 7) // 8 == 2   # 9 fields = 2 bytes
    assert (16 + 7) // 8 == 2  # 16 fields = 2 bytes
    assert (17 + 7) // 8 == 3  # 17 fields = 3 bytes


def test_bitvector_bit_masking():
    """Test individual bit operations."""
    bv = 0

    bv = set_bit(bv, 0)
    assert is_bit_set(bv, 0)
    assert bv == 0b00000001

    bv = set_bit(bv, 7)
    assert is_bit_set(bv, 7)
    assert bv == 0b10000001

    bv = clear_bit(bv, 0)
    assert not is_bit_set(bv, 0)
    assert bv == 0b10000000
```

### Integration Tests for Delta Protocol

```python
def test_delta_first_packet_populates_cache(cache):
    """First packet should populate cache with all field values."""
    spec = create_test_spec(num_fields=5)
    payload = build_payload_all_fields_present(spec, key=1, values=[10, 20, 30, 40, 50])

    result = decode_delta_packet(payload, spec, cache)

    # Verify all fields decoded correctly
    assert result['f0'] == 10
    assert result['f4'] == 50

    # Verify cache populated
    cached = cache.get_cached_packet(spec.packet_type, (1,))
    assert cached is not None
    assert cached['f0'] == 10


def test_delta_second_packet_uses_cache(cache):
    """Second packet should reuse cached values for unchanged fields."""
    spec = create_test_spec(num_fields=5)

    # First packet: all fields present
    payload1 = build_full_payload(spec, key=1, values=[10, 20, 30, 40, 50])
    result1 = decode_delta_packet(payload1, spec, cache)

    # Second packet: only field 2 changed
    payload2 = build_partial_payload(spec, key=1, changed_fields={2: 99})
    result2 = decode_delta_packet(payload2, spec, cache)

    # Verify field 2 updated
    assert result2['f2'] == 99

    # Verify other fields from cache
    assert result2['f0'] == 10  # From cache
    assert result2['f1'] == 20  # From cache
    assert result2['f3'] == 40  # From cache
    assert result2['f4'] == 50  # From cache


def test_delta_cache_isolation_by_key(cache):
    """Verify separate cache entries for different keys."""
    spec = create_test_spec(num_fields=3)

    # Decode entity with key=1
    payload1 = build_full_payload(spec, key=1, values=[100, 200, 300])
    decode_delta_packet(payload1, spec, cache)

    # Decode entity with key=2
    payload2 = build_full_payload(spec, key=2, values=[10, 20, 30])
    decode_delta_packet(payload2, spec, cache)

    # Verify separate cache entries
    cached1 = cache.get_cached_packet(spec.packet_type, (1,))
    cached2 = cache.get_cached_packet(spec.packet_type, (2,))

    assert cached1['f0'] == 100
    assert cached2['f0'] == 10


def test_delta_boolean_header_folding(cache):
    """Verify BOOL fields read from bitvector, not payload."""
    spec = PacketSpec(
        packet_type=100,
        fields=[
            FieldSpec('id', 'UINT32', is_key=True),
            FieldSpec('is_active', 'BOOL'),
            FieldSpec('is_visible', 'BOOL'),
            FieldSpec('count', 'SINT16'),
        ]
    )

    # Bitvector: 0b00000101
    # - bit 0 (is_active) = 1 → True
    # - bit 1 (is_visible) = 0 → False
    # - bit 2 (count) = 1 → present
    payload = encode_uint32(1) + b'\x05' + encode_sint16(10)

    result = decode_delta_packet(payload, spec, cache)

    assert result['is_active'] == True
    assert result['is_visible'] == False
    assert result['count'] == 10
```

### Fuzzing and Property-Based Tests

```python
@pytest.mark.slow
def test_delta_random_field_combinations(cache):
    """Test random combinations of present/absent fields."""
    spec = create_large_test_spec(num_fields=50)

    for trial in range(100):
        key = random.randint(0, 1000)
        fields_present = random.sample(range(50), k=random.randint(1, 50))
        field_values = generate_random_values(spec)

        payload = build_test_payload(spec, key, fields_present, field_values)
        result = decode_delta_packet(payload, spec, cache)

        verify_result(result, fields_present, field_values, cache)


def test_delta_encode_decode_roundtrip(cache):
    """Property: encode(decode(x)) should equal x."""
    spec = create_test_spec(num_fields=10)
    original_fields = {'id': 42, 'f0': 1, 'f1': 2, 'f2': 3, ...}

    # Encode
    encoded = encode_delta_packet(original_fields, spec, cache)

    # Decode
    decoded = decode_delta_packet(encoded, spec, cache)

    # Verify roundtrip
    assert decoded == original_fields
```

### Performance Tests

```python
def test_delta_bandwidth_savings():
    """Measure bandwidth savings from delta protocol."""
    spec = create_realistic_city_spec()  # 100+ fields

    # First packet (full)
    payload_full = build_full_payload(spec)
    size_full = len(payload_full)

    # Subsequent packets (2-3 fields changed)
    payload_delta = build_delta_payload(spec, num_changed=3)
    size_delta = len(payload_delta)

    savings_percent = 100 * (1.0 - size_delta / size_full)

    assert savings_percent > 90  # Should save 90%+ bandwidth
    print(f"Bandwidth savings: {savings_percent:.1f}%")


def test_delta_cache_memory_usage():
    """Measure cache memory for realistic game."""
    cache = DeltaCache()

    # Simulate 200 cities
    for city_id in range(200):
        fields = generate_realistic_city_fields(city_id)
        encode_delta_packet(fields, CITY_INFO_SPEC, cache)

    cache_size_bytes = estimate_cache_size(cache)
    cache_size_kb = cache_size_bytes / 1024

    assert cache_size_kb < 500  # Should be under 500KB
    print(f"Cache size for 200 cities: {cache_size_kb:.1f} KB")
```

---

## Summary

### Key Takeaways

1. **Delta protocol reduces bandwidth by 60-90%** by transmitting only changed fields
2. **Bitvectors use little-endian bit order** within each byte
3. **Key fields are always transmitted** and used for cache indexing
4. **BOOL fields use header folding** - bit value IS the field value (no payload bytes)
5. **Cache is keyed by `(packet_type, key_tuple)`** allowing multiple instances
6. **First packet populates cache**, subsequent packets use delta encoding
7. **Clear cache on disconnect** to ensure clean state

### Quick Reference

```python
# Read bitvector (little-endian!)
num_bytes = (num_bits + 7) // 8
bitvector = int.from_bytes(data[offset:offset+num_bytes], byteorder='little')

# Test bit
is_present = (bitvector & (1 << bit_index)) != 0

# Decode delta packet
# 1. Read key fields (always present)
# 2. Read bitvector
# 3. Get cached packet or use defaults
# 4. For each non-key field:
#    - If BOOL: use bit value from bitvector
#    - Elif bit set: read from payload
#    - Else: use cached value
# 5. Update cache
```

### Common Issues Checklist

- [ ] Using little-endian for bitvector (not big-endian)
- [ ] BOOLs read from bitvector (not payload)
- [ ] Only non-key fields in bitvector
- [ ] Handling cache misses with defaults
- [ ] Copying dicts when storing in cache
- [ ] Clearing cache on disconnect

---

## References

- **FreeCiv Source:** `/home/jd/development/freeciv-ai/freeciv/`
  - `common/networking/packets.def` - Packet specifications
  - `common/generate_packets.py` - Code generator for delta protocol
  - `utility/bitvector.h` - Bitvector macros and functions
  - `common/networking/dataio_raw.h` - Network I/O functions
  - `doc/README.delta` - Delta protocol documentation

- **This Project:**
  - `fc_client/protocol.py` - Protocol encoding/decoding
  - `fc_client/packet_specs.py` - Packet specifications
  - `fc_client/delta_cache.py` - Cache implementation
  - `CLAUDE.md` - Project documentation

---

## Related Protocol Features

The delta protocol is one of several bandwidth optimization techniques used by FreeCiv. This section cross-references related features.

### Packet Compression

**⚠️ CRITICAL: Our client does NOT implement packet compression yet! ⚠️**

FreeCiv uses DEFLATE compression to bundle multiple packets together, providing an additional 60-90% bandwidth reduction on top of delta protocol savings.

**How it works:**
- Server sends `PACKET_FREEZE_CLIENT` (130) to start compression grouping
- Multiple packets (including delta-encoded packets) are queued
- Queued packets compressed together using zlib DEFLATE
- Compressed data sent as single "packet" with special header
- Server sends `PACKET_THAW_CLIENT` (131) to end compression

**Compression detection:**
```python
# Read packet length field
length = struct.unpack('<H', header_bytes[:2])[0]

if length == 65535:  # JUMBO_SIZE
    # Jumbo compressed packet (>48KB)
    actual_length = struct.unpack('<I', next_4_bytes)[0]

elif length >= 16385:  # COMPRESSION_BORDER
    # Normal compressed packet
    actual_length = length - 16385

else:
    # Uncompressed packet
    # Process normally with delta protocol if applicable
```

**Interaction with delta protocol:**
- Compression happens AFTER delta encoding
- Server first applies delta protocol to individual packets
- Then compresses multiple delta packets together
- Client decompresses first, then applies delta decoding to each packet

**For complete details, see:**
- `CLAUDE.md` - Section "Packet Compression System"
- `freeciv/common/networking/packets.c:442-504` - Server compression implementation
- `freeciv/doc/README.delta` lines 42-74 - Compression documentation

**Current status:**
- ❌ Not implemented in our client
- 🔴 CRITICAL PRIORITY - Required for production use
- 📝 Implementation blocked until compression support added to `fc_client/protocol.py`

### Combined Optimization Impact

When both delta protocol and compression are used:

**Typical bandwidth savings:**
```
Original packet size:     1000 bytes
After delta protocol:     100 bytes  (90% reduction)
After compression:        20 bytes   (80% reduction of delta)
Total reduction:          98%        (combined effect)
```

**Real-world example (PACKET_CITY_INFO with 100+ fields):**
- Full packet: ~2000 bytes
- Delta (2-3 fields changed): ~50 bytes (97.5% reduction)
- Compressed (with 20 other packets): ~10 bytes effective (99.5% reduction)

### Protocol Feature Summary

| Feature | Purpose | Savings | Status in Our Client |
|---------|---------|---------|---------------------|
| Delta Protocol | Transmit only changed fields | 60-90% | ✅ Implemented |
| Array-Diff | Transmit only changed array elements | 50-80% (for arrays) | ❌ Not implemented |
| Compression | Bundle multiple packets with DEFLATE | 60-90% (on top of delta) | ❌ Not implemented |
| Boolean Folding | Store BOOL values in bitvector | 8x (for booleans) | ✅ Implemented |

**Implementation priority for remaining features:**
1. **Packet Compression** (CRITICAL - blocks production use)
2. **Array-Diff** (HIGH - blocks ~50+ packet types)

---

**End of Document**
