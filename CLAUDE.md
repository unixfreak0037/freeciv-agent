# CLAUDE.md

This file provides guidance to Claude Code when working with this FreeCiv AI client.

## Project Overview

Python-based AI client for FreeCiv, a turn-based strategy game. Implements the FreeCiv network protocol over TCP using asyncio.

**FreeCiv source code** is available in `freeciv/` directory for reference - DO NOT edit these files.

## Quick Start

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
python3 fc_ai.py

# Debug packets
python3 fc_ai.py --debug-packets

# Test
pytest
pytest --cov=fc_client --cov-report=html
```

## Critical Architecture Constraints

### ASYNC EVERYTHING

**This project uses Python asyncio for ALL I/O operations.**

- All network I/O MUST use async/await
- Use `asyncio.StreamReader` and `asyncio.StreamWriter`
- Always `await writer.drain()` after `writer.write()`
- Use `asyncio.wait_for()` for timeouts
- Only call `asyncio.run()` once at top level (fc_ai.py)

```python
# Correct pattern
async def read_data(reader: asyncio.StreamReader) -> bytes:
    data = await reader.readexactly(num_bytes)
    return data

async def send_data(writer: asyncio.StreamWriter, data: bytes):
    writer.write(data)
    await writer.drain()
```

## FreeCiv Protocol Implementation - CRITICAL

**When implementing protocol features, consult sources in this order:**

### 1. Captured packets from real server (GROUND TRUTH)
```bash
python3 fc_ai.py --debug-packets
xxd packets/inbound_*_typeNNN.packet
```
Real server behavior is the ONLY definitive source.

### 2. Generated C code (AUTHORITATIVE) - freeciv-build directory
```bash
# Find the receive (decode) function for your packet
grep -n "receive_packet_<name>_100" freeciv-build/packets_gen.c

# Read the implementation (replace NNNN with line number from grep)
sed -n 'NNNN,+150p' freeciv-build/packets_gen.c

# Find the struct definition
grep -A 20 "struct packet_<name> {" freeciv-build/packets_gen.h
```

**Key Files:**
- `freeciv-build/packets_gen.c` (2.8 MB) - Complete encoder/decoder implementations
- `freeciv-build/packets_gen.h` (83 KB) - Struct definitions with field types

**What to Look For:**
- `DIO_BV_GET()` - Bitvector read (always first!)
- `BV_ISSET(fields, N)` - Field N is conditional (in bitvector)
- `DIO_GET(uint8)`, `DIO_GET(uint16)`, `DIO_GET(string)` - Field encoding types
- Field order in `BV_ISSET()` blocks matches bitvector bit indices

### 3. Code generator (REVEALS IMPLEMENTATION DETAILS)
- `freeciv/common/generate_packets.py` - Shows encoding rules, field order, optimizations
- Example: Lines 2267-2282 show bitvector is transmitted BEFORE key fields
- Example: Lines 1590-1730 show boolean header folding

### 4. packets.def (DO NOT TRUST - LAST RESORT ONLY)
- `freeciv/common/networking/packets.def` - **OFTEN WRONG OR INCOMPLETE**
- Use ONLY for packet numbers and type mappings
- **NEVER implement based solely on packets.def without verification**
- Example failure: PACKET_RULESET_GAME (141) specification was completely wrong

**Lesson learned:** We wasted hours implementing based on packets.def, only to discover the actual packet structure was completely different. Always start with captured packets or generated code.

### Implementing New Packet Handlers

When you need to implement a new packet handler, use the **packet-handler-builder** agent.

### How to Use freeciv-build Generated Files

**Step 1: Locate the packet decoder**
```bash
# Example: Finding PACKET_RULESET_TRADE decoder
grep -n "receive_packet_ruleset_trade_100" freeciv-build/packets_gen.c
# Output: 68298:static struct packet_ruleset_trade *receive_packet_ruleset_trade_100
```

**Step 2: Read the implementation**
```bash
# Read ~150 lines starting from the function (adjust count as needed)
sed -n '68298,68450p' freeciv-build/packets_gen.c
```

**Step 3: Identify encoding pattern**

Look for these patterns in order:
1. **Bitvector read**: `DIO_BV_GET(&din, &field_addr, fields);`
2. **Conditional field reads**: `if (BV_ISSET(fields, 0)) { DIO_GET(uint8, ..., &real_packet->id); }`
3. **Field types**: uint8, uint16, uint32, sint16, string, bool8
4. **Array loops**: `for (i = 0; i < count; i++) { DIO_GET(...); }`

**Step 4: Check struct definition for context**
```bash
grep -A 10 "struct packet_ruleset_trade {" freeciv-build/packets_gen.h
```

This shows field types and enum annotations that reveal semantic meaning.

## Delta Protocol Essentials

For detailed documentation, see [freeciv/doc/README.delta](freeciv/doc/README.delta).

### Critical Implementation Details

**Field Transmission Order:**
1. Bitvector (indicates which non-key fields are present)
2. Key fields (always present)
3. Non-key fields (conditional, based on bitvector)

**Boolean Header Folding:**
- Standalone BOOL fields: bitvector bit IS the value
- NO payload bytes consumed for standalone BOOL fields
- BOOL arrays still transmit each element as a byte

**Bitvector Byte Order:**
```python
# CORRECT: Little-endian
bitvector = int.from_bytes(bitvector_bytes, byteorder='little')

# WRONG: Big-endian will decode fields incorrectly
```

**Cache Structure:**
```python
cache = {
    (packet_type, key_tuple): {
        'field1': value1,
        'field2': value2,
        # ... other fields
    }
}
```

## Testing Infrastructure

Tests organized in `tests/`: `unit/`, `async/`, `integration/`

All configuration in `pyproject.toml`:
- `asyncio_mode = "auto"` - No need for `@pytest.mark.asyncio`
- Coverage configured for `fc_client/` package
- Black formatting: 100 char line length

**Shared fixtures in `tests/conftest.py`:**
- `mock_stream_reader`, `mock_stream_writer`, `mock_stream_pair`
- `delta_cache`, `game_state`, `freeciv_client`
- Sample packet data fixtures

### Testing Guidelines

**IMPORTANT: Tests should reflect expected behavior, not work around bugs.**

When tests fail:
1. **Never modify tests to accommodate obvious bugs** - fix the implementation
2. **Fix obvious bugs directly** - incorrect logic, typos, wrong values
3. **Ask for guidance when uncertain** - bug vs misunderstanding vs incorrect test
4. **FreeCiv server is source of truth** - consult `freeciv/` source code
5. **Stop and ask about server bugs** - document and ask before workaround

## Core Components

- **fc_ai.py**: Entry point, uses `asyncio.run()` to execute main loop
- **fc_client/client.py**: `FreeCivClient` class with async TCP connection management
  - `async connect()`, `async disconnect()`, `async join_game()`
  - `async _packet_reader_loop()`: Background task for packet processing
  - Event-based packet dispatch with handler registration
  - Dynamic protocol version switching (1-byte → 2-byte after JOIN_REPLY)
- **fc_client/protocol.py**: Packet encoding/decoding
  - `async read_packet()`: Reads from StreamReader with protocol version support
  - `decode_delta_packet()`: Delta protocol with bitvector and cache
  - Synchronous encode/decode functions for specific packets
- **fc_client/handlers/**: Packet handler functions
- **fc_client/packet_specs.py**: Declarative packet specifications
- **fc_client/delta_cache.py**: Delta protocol cache management
- **fc_client/game_state.py**: Game state tracking
- **fc_client/packet_debugger.py**: Optional packet capture for debugging

## Packet Debugging

Captures raw packets to `packets/` directory with format: `DIRECTION_INDEX_typeNNN.packet`

Examples:
- `inbound_0001_type005.packet` - First inbound packet, type 5 (SERVER_JOIN_REPLY)
- `outbound_0001_type004.packet` - First outbound packet, type 4 (SERVER_JOIN_REQ)

**Use for:**
- Implementing new packet handlers (use real bytes as test fixtures)
- Debugging decoding errors
- Protocol analysis
- Writing unit tests with known-good data

## Dependencies

**Runtime:** Python 3.7+ (asyncio support), standard library only

**Development:**
- `black` - Code formatting
- `pytest`, `pytest-asyncio`, `pytest-cov` - Testing

## Key Pitfalls to Avoid

1. ❌ Reading key fields before bitvector (bitvector comes first)
2. ❌ Reading payload bytes for standalone BOOL fields (use bitvector bit)
3. ❌ Using big-endian for bitvector (FreeCiv uses little-endian)
4. ❌ Trusting packets.def field order (verify with generated C code)
5. ❌ Implementing based on packets.def without verification (ALWAYS capture real packets)
6. ❌ Using sync I/O instead of async/await (ALL I/O must be async)
7. ❌ Forgetting `await writer.drain()` after `writer.write()`
8. ❌ Creating synthetic test data (use real captured packets)
