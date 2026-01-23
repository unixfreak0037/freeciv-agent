# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based AI client for FreeCiv, a turn-based strategy game. The project implements a network client that connects to FreeCiv servers via TCP sockets and implements the FreeCiv network protocol.

## Development Environment

### Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# .venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Client
```bash
# Run the main AI client
python3 fc_ai.py
```

### Freeciv Source Code

The source code for freeciv is located in the `freeciv` directory. It is made available so that questions can be answered as we develop this project.

- Do not edit the files in this directory.

## Architecture

### Async Architecture

**IMPORTANT: This project uses Python's `asyncio` for all I/O operations.**

- All network I/O operations MUST use async/await
- Use `asyncio.StreamReader` and `asyncio.StreamWriter` for network communication
- Any new I/O-related functionality (file I/O, network requests, etc.) MUST be implemented as async
- The entire call chain from entry point through network operations is async

### Core Components

- **fc_ai.py**: Async entry point script that initializes and runs the FreeCiv AI client
  - Creates a `FreeCivClient` instance
  - Uses `asyncio.run()` to execute the async main loop
  - Awaits all async client operations (connect, join_game, disconnect)

- **fc_client/**: Package containing the FreeCiv client implementation
  - **client.py**: Core `FreeCivClient` class that manages async TCP connections to FreeCiv servers
    - `async connect()`: Establishes TCP connection using `asyncio.open_connection()`
    - `async disconnect()`: Closes connection gracefully with `writer.close()` and `await writer.wait_closed()`
    - `async join_game()`: Sends JOIN_REQ packet and waits for server response with timeout handling
    - `async _packet_reader_loop()`: Background task that continuously reads and dispatches packets
    - Event-based packet dispatch system with handler registration
    - Dynamic protocol version switching (1-byte → 2-byte packet types after JOIN_REPLY)
    - Signal handling (SIGINT/SIGTERM) for graceful shutdown
  - **protocol.py**: Protocol encoding/decoding functions
    - `async read_packet()`: Reads packets from `asyncio.StreamReader` with protocol version support
    - `async _recv_exact()`: Ensures exact number of bytes are read using `reader.readexactly()`
    - `decode_delta_packet()`: Decodes delta-compressed packets using bitvectors and cache
    - `read_bitvector()`, `is_bit_set()`: Bitvector utilities for delta protocol
    - `_decode_field()`: Generic field decoder for all FreeCiv data types
    - Synchronous encoding functions: `encode_packet()`, `encode_server_join_req()`, etc.
    - Synchronous decoding functions: `decode_server_join_reply()`, `decode_server_info()`, `decode_chat_msg_packet()`, etc.
  - **handlers.py**: Packet handler functions registered for different packet types
    - `handle_processing_started()`, `handle_processing_finished()`: Capability negotiation handlers
    - `handle_server_join_reply()`: Handles join response and switches protocol version
    - `handle_server_info()`: Processes server information and updates game state
    - `handle_chat_msg()`: Handles chat messages from server and other players
    - `handle_unknown_packet()`: Default handler for unimplemented packet types
  - **packet_specs.py**: Declarative packet specification system
    - `FieldSpec`: Defines structure of individual packet fields (name, type, size)
    - `PacketSpec`: Complete packet specification with type number and field list
    - Centralized packet definitions for SERVER_INFO (25) and CHAT_MSG (29)
  - **delta_cache.py**: Delta protocol cache for bandwidth optimization
    - `DeltaCache`: Manages cached packet data keyed by (packet_type, key_value)
    - Stores previous packet field values for delta decoding
    - Cache cleared on disconnect to maintain consistency
  - **game_state.py**: Game state tracking
    - `GameState`: Tracks server_info dict and chat_history list
    - Updated by packet handlers as game progresses
  - **packet_debugger.py**: Optional packet capture utility for debugging
    - `PacketDebugger`: Captures raw packets to files for analysis
    - Enabled via `--debug-packets` command-line flag
    - Saves packets with format: `DIRECTION_INDEX_typeNNN.packet` (e.g., `inbound_0001_type005.packet`)
    - Includes packet type in filename for easy identification

### FreeCiv Protocol

**CRITICAL: When implementing protocol features, consult sources in this order:**

1. **Captured packets from real server** - The ultimate source of truth
   - Run `python3 fc_ai.py --debug-packets` to capture actual packet bytes
   - Examine raw bytes with `xxd packets/inbound_*_typeNNN.packet`
   - Real server behavior is the ONLY definitive source

2. **Generated C code** - The actual protocol implementation
   - `freeciv/common/packets_gen.c` - Generated send/receive functions
   - `freeciv/common/packets_gen.h` - Generated packet structures
   - This shows HOW packets are actually encoded/decoded by the server
   - Search for `send_packet_<name>` and `receive_packet_<name>` functions

3. **freeciv/common/generate_packets.py** (lines 1-3000+) - The code generator
   - Shows packet generation logic (field order, encoding rules, optimizations)
   - Reveals implementation details not in specifications
   - Example: Lines 2267-2282 show bitvector is transmitted BEFORE key fields
   - Example: Lines 1590-1730 show boolean header folding implementation

4. **freeciv/common/networking/packets.def** (2477 lines) - DO NOT TRUST AS PRIMARY SOURCE
   - ⚠️ **WARNING:** packets.def is often WRONG or INCOMPLETE
   - Example: PACKET_RULESET_GAME (141) specification shows fields that don't exist in actual packets
   - Use ONLY as a last resort for high-level overview
   - NEVER implement based solely on packets.def without verification
   - Packet numbers and type mappings are usually accurate
   - Field lists, field order, and conditional fields are UNRELIABLE

**Why this order matters:**
- packets.def is a specification that may not match actual implementation
- The generated C code is what the server actually runs
- Real captured packets prove what's actually transmitted
- **LESSON LEARNED:** We wasted hours implementing PACKET_RULESET_GAME based on packets.def, only to discover the actual packet structure was completely different. Always start with captured packets or generated code.

### Current State

The project has a working async network client that can connect to FreeCiv servers and join games. Current implementation status:

**Completed:**
1. ✅ Async network architecture using `asyncio` with StreamReader/StreamWriter
2. ✅ TCP connection to FreeCiv servers
3. ✅ Packet encoding/decoding for JOIN_REQ, JOIN_REPLY, SERVER_INFO, CHAT_MSG packets
4. ✅ Delta protocol support for bandwidth optimization
5. ✅ Successful game join with username "ai-user"
6. ✅ Timeout handling for network operations
7. ✅ Graceful connection cleanup with signal handling (SIGINT/SIGTERM)
8. ✅ Event-driven packet processing with handler registration system
9. ✅ Basic game state tracking (server info, chat history)
10. ✅ Packet debugger utility for network protocol analysis

**To Do:**
1. **Protocol Implementation**: Implement encoding/decoding for remaining ~515 packet types (packet type numbers from `packets.def`, but structure must be verified from captured packets and generated C code)
2. **Game State Management**: Expand tracking to include players, cities, units, map tiles, etc.
3. **AI Strategy**: Implement AI decision-making logic for game actions
4. **Turn Management**: Handle turn-based game loop and action submission
5. **Action Encoding**: Implement packet encoding for player actions (move unit, build, etc.)

### Implementation Status and Priorities

This section tracks the implementation status of FreeCiv protocol features and prioritizes future work.

**✅ Implemented Features:**

1. **Basic Delta Protocol**
   - Bitvector-based field presence indication
   - Key field / non-key field handling
   - Delta cache for bandwidth optimization
   - Field transmission order: bitvector → key fields → non-key fields
   - Implemented for: PACKET_SERVER_INFO (25), PACKET_CHAT_MSG (29)

2. **Boolean Header Folding**
   - BOOL field values stored in bitvector bits
   - No payload bytes consumed for standalone BOOL fields
   - 8x compression for boolean data
   - Correctly handles BOOL vs BOOL array distinction

3. **Basic Packet Handlers**
   - PACKET_PROCESSING_STARTED (0)
   - PACKET_PROCESSING_FINISHED (1)
   - PACKET_SERVER_JOIN_REPLY (5)
   - PACKET_SERVER_INFO (25) with delta support
   - PACKET_CHAT_MSG (29) with delta support

4. **Protocol Infrastructure**
   - Async network I/O with asyncio
   - Dynamic protocol version switching (1-byte → 2-byte packet types)
   - Event-driven packet dispatch system
   - Packet debugger for capturing raw server packets
   - Delta cache management

**❌ CRITICAL MISSING FEATURES:**

1. **Packet Compression (HIGHEST PRIORITY)**
   - Status: ❌ Not implemented
   - Impact: **BLOCKS production use** - Real servers compress bulk updates
   - Severity: 🔴 CRITICAL - Client will fail with compressed packets
   - Required for: Game start, end of turn, reconnect scenarios
   - Dependencies: Python zlib module (already in stdlib)
   - Estimated effort: Medium (1-2 days implementation + testing)
   - Implementation location: `fc_client/protocol.py`
   - References: `freeciv/common/networking/packets.c:442-504`, `freeciv/doc/README.delta:42-74`

   **Next Steps:**
   - Implement compression detection in `read_packet()`
   - Add zlib decompression function
   - Handle recursive packet parsing from decompressed buffer
   - Test with real FreeCiv server in large game scenarios
   - Add PACKET_FREEZE_CLIENT (130) and PACKET_THAW_CLIENT (131) handlers

**❌ IMPORTANT MISSING FEATURES:**

2. **Array-Diff Optimization (HIGH PRIORITY)**
   - Status: ❌ Not implemented
   - Impact: Required for complex ruleset packets (PACKET_RULESET_GAME, etc.)
   - Severity: 🟡 HIGH - Blocks implementation of ~50+ packet types
   - Required for: Ruleset packets, technology trees, unit definitions
   - Dependencies: None
   - Estimated effort: Small (1 day implementation + testing)
   - Implementation location: `fc_client/protocol.py`
   - References: `freeciv/common/generate_packets.py:1273-1441`, `freeciv/doc/README.delta:23-29`

   **Next Steps:**
   - Implement generic array-diff decoder
   - Parse packets.def to identify diff-marked arrays
   - Add diff array support to field decoder
   - Test with PACKET_RULESET_GAME veteran_name array

3. **Additional Packet Handlers (~515 types)**
   - Status: ❌ Only 5 of ~520 packet types implemented
   - Impact: Limited game functionality - can join but not play
   - Severity: 🟡 HIGH - Blocks AI gameplay
   - Required for: Full game participation, AI decision-making
   - Dependencies: Compression and array-diff must be implemented first
   - Estimated effort: Large (ongoing work, prioritize by gameplay needs)

   **Priority packet types to implement:**
   - PACKET_PLAYER_INFO (43) - Track player state
   - PACKET_TILE_INFO (30) - Map visibility
   - PACKET_UNIT_INFO (26) - Unit tracking
   - PACKET_CITY_INFO (31) - City management
   - PACKET_RULESET_* (141-200+) - Game rules (requires array-diff)

**🔮 NICE TO HAVE FEATURES:**

4. **PACKET_FREEZE_CLIENT / PACKET_THAW_CLIENT Handling**
   - Status: ❌ Not handled (packets ignored)
   - Impact: GUI update batching not implemented (not critical for headless AI)
   - Severity: 🟢 LOW - Useful for debugging and optimization
   - Required for: Understanding compression boundaries, optimal state updates

   **Next Steps:**
   - Add basic handlers that log when compression grouping starts/ends
   - Optionally batch state updates between FREEZE/THAW

5. **Capability Variants**
   - Status: ❌ Not implemented
   - Impact: May encounter different packet field sets from different server versions
   - Severity: 🟢 LOW - Current implementation works with FreeCiv 3.2.2
   - Required for: Supporting multiple FreeCiv server versions

   **Next Steps:**
   - Document when packet variations are encountered
   - Implement variant handling if server compatibility issues arise

**Implementation Roadmap:**

```
Phase 1 (CRITICAL - Blocks production):
├─ 1. Packet Compression
│  ├─ Implement compression detection
│  ├─ Add zlib decompression
│  ├─ Handle recursive packet parsing
│  └─ Test with real server

Phase 2 (HIGH - Enables complex packets):
├─ 2. Array-Diff Optimization
│  ├─ Implement array-diff decoder
│  ├─ Identify diff arrays in packets.def
│  └─ Test with ruleset packets

Phase 3 (ONGOING - Enables gameplay):
├─ 3. Core Gameplay Packets
│  ├─ PACKET_PLAYER_INFO (43)
│  ├─ PACKET_TILE_INFO (30)
│  ├─ PACKET_UNIT_INFO (26)
│  ├─ PACKET_CITY_INFO (31)
│  └─ Movement/action packets

Phase 4 (ONGOING - Full protocol):
├─ 4. Ruleset Packets (requires array-diff)
│  ├─ PACKET_RULESET_GAME (141)
│  ├─ PACKET_RULESET_TECH (148)
│  ├─ PACKET_RULESET_UNIT (149)
│  └─ Additional ruleset packets

Phase 5 (OPTIONAL - Polish):
├─ 5. Freeze/Thaw Handlers
└─ 6. Capability Variants
```

**Testing Requirements:**

Before considering each phase complete:
- ✅ Unit tests with captured real server packets
- ✅ Integration tests with mock server
- ✅ Manual testing with real FreeCiv server
- ✅ Coverage report showing >80% for new code
- ✅ No regressions in existing packet handlers

## Dependencies

**Runtime Dependencies:**
- Python 3.7+ (for `asyncio` support)
- No external packages required - uses Python standard library only

**Development/Testing:**
- `black` - Code formatter for consistent style
- `pytest` - Testing framework
- `pytest-asyncio` - Support for testing async functions
- `pytest-cov` - Code coverage reporting

## Testing Infrastructure

The project uses pytest with async support for comprehensive testing of the FreeCiv AI client.

### Test Organization

Tests are organized into three categories based on complexity and I/O requirements:

```
tests/
├── __init__.py          # Test suite documentation
├── conftest.py          # Shared fixtures for all tests
├── unit/                # Pure unit tests (fast, no I/O)
│   └── __init__.py
├── async/               # Async tests with mocked I/O
│   └── __init__.py
└── integration/         # Integration tests (cross-module)
    └── __init__.py
```

**Directory Purposes:**
- **unit/**: Test pure functions like encoders, decoders, and data structures. No network I/O, fast execution.
- **async/**: Test async logic with mocked `StreamReader`/`StreamWriter` to avoid real network calls.
- **integration/**: Test full packet processing pipelines across multiple modules.

### Configuration

All test configuration is centralized in `pyproject.toml` (modern Python standard):

**pytest Configuration:**
- `asyncio_mode = "auto"`: Automatically detects async test functions without requiring `@pytest.mark.asyncio` decorator
- Custom markers: `unit`, `async_test`, `integration`, `network`, `slow`
- Test discovery: `tests/` directory with `test_*.py` pattern

**Coverage Configuration:**
- Source tracking: `fc_client/` package
- Branch coverage enabled
- HTML reports in `htmlcov/` directory
- Excludes: `tests/`, `freeciv/` (reference code), `packets/` (debug output)

**Black Configuration:**
- Line length: 100 characters
- Excludes: `freeciv/`, `packets/`, `.venv/`, test artifacts

### Running Tests

```bash
# Activate virtual environment first
source .venv/bin/activate

# Run all tests
pytest

# Run specific test directory
pytest tests/unit
pytest tests/async
pytest tests/integration

# Run with coverage report
pytest --cov=fc_client --cov-report=html

# Run tests matching a pattern
pytest -k test_encode_packet

# Run tests with specific marker
pytest -m unit           # Only unit tests
pytest -m "not slow"     # Skip slow tests

# Verbose output with traceback
pytest -v --tb=short
```

### Shared Fixtures

The `tests/conftest.py` file provides reusable fixtures to minimize test boilerplate:

**Mock Network Fixtures:**
- `mock_stream_reader`: Mocked `asyncio.StreamReader` with `readexactly()`, `read()`, `at_eof()`
- `mock_stream_writer`: Mocked `asyncio.StreamWriter` with `write()`, `drain()`, `close()`, `wait_closed()`
- `mock_stream_pair`: Convenience fixture providing both reader and writer

**Component Fixtures:**
- `delta_cache`: Fresh `DeltaCache` instance for testing delta protocol
- `game_state`: Fresh `GameState` instance for testing state tracking
- `freeciv_client`: Mock `FreeCivClient` with injected dependencies (no active connection)

**Sample Data Fixtures:**
- `sample_join_reply_success`: Sample SERVER_JOIN_REPLY packet data (successful join)
- `sample_join_reply_failure`: Sample SERVER_JOIN_REPLY packet data (failed join)
- `sample_server_info`: Sample SERVER_INFO packet data with game state
- `sample_chat_msg_payload`: Sample CHAT_MSG packet data
- `sample_bitvector`: Sample bitvector bytes for delta protocol testing

**Utility Fixtures:**
- `packet_builder`: Helper function to construct raw packet bytes with header + body

### Test Markers

Tests can be marked with custom markers for selective execution:

```python
import pytest

@pytest.mark.unit
def test_encode_string():
    # Fast unit test with no I/O
    pass

@pytest.mark.async_test
async def test_read_packet(mock_stream_reader):
    # Async test with mocked I/O
    pass

@pytest.mark.integration
@pytest.mark.slow
async def test_full_packet_pipeline():
    # Integration test across multiple modules
    pass
```

**Marker Definitions:**
- `@pytest.mark.unit`: Fast unit tests with no I/O operations
- `@pytest.mark.async_test`: Async tests with mocked StreamReader/StreamWriter
- `@pytest.mark.integration`: Integration tests across multiple modules
- `@pytest.mark.network`: Tests requiring network stream mocking
- `@pytest.mark.slow`: Slow-running tests (skip with `-m "not slow"`)

### Coverage Reports

After running tests with coverage, view results:

```bash
# Terminal summary
pytest --cov=fc_client --cov-report=term

# Generate HTML report
pytest --cov=fc_client --cov-report=html

# Open HTML report in browser
xdg-open htmlcov/index.html  # Linux
open htmlcov/index.html       # macOS
```

Coverage artifacts are ignored by git:
- `.pytest_cache/` - Pytest cache directory
- `htmlcov/` - HTML coverage reports
- `.coverage` - Coverage data file

### Design Rationale

**Why pyproject.toml over pytest.ini:**
- Modern Python standard (PEP 518/517/621)
- Single configuration file for all tools (pytest, coverage, black)
- Future-proof as ecosystem moves away from legacy config files

**Why asyncio_mode = "auto":**
- Eliminates need for `@pytest.mark.asyncio` decorator on every async test
- Automatically detects async test functions by signature
- Reduces boilerplate and improves test readability

**Why three test directories:**
- Clear separation between fast unit tests and slower integration tests
- Allows running subsets of tests during development (e.g., `pytest tests/unit` for quick feedback)
- Encourages writing fast unit tests for pure functions before integration tests

**Why comprehensive fixtures:**
- Reduces test boilerplate by providing pre-configured mocks and sample data
- Ensures consistent test setup across all test files
- Makes tests more readable by focusing on behavior rather than setup

### Debugging Test Failures and Bugs

**IMPORTANT: Tests should reflect expected behavior, not work around implementation bugs.**

When encountering test failures, follow these guidelines:

1. **Never modify tests to accommodate obvious bugs**: If a test fails due to a clear bug in the implementation code, fix the bug in the implementation, not the test.

2. **Fix obvious bugs directly**: When you identify an obvious bug (incorrect logic, typos, wrong return values, etc.), go ahead and fix it in the implementation code.

3. **Ask for guidance when uncertain**: If it's unclear whether the issue is:
   - A bug in the implementation
   - A misunderstanding of requirements
   - An incorrect test expectation

   Stop and ask for clarification before making changes.

4. **Consider the FreeCiv server as a source of truth**: We're implementing a client that communicates with a FreeCiv game server. The server behavior defines the correct protocol implementation.
   - The FreeCiv source code is available in the `freeciv/` directory for validation
   - If server behavior seems unexpected, consult the source code to verify
   - The server itself may have bugs, but we should match its actual behavior

5. **Stop and ask about server bugs**: If you discover what appears to be a bug in the FreeCiv server itself:
   - Document the unexpected behavior
   - Reference the relevant server source code
   - Stop and ask whether to:
     - Implement a workaround in the client
     - Report the issue upstream
     - Document the behavior and move on

**Example Scenarios:**

- ❌ **Wrong**: Test expects `decode_packet()` to return a dict, but it returns a tuple. Change the test to expect a tuple.
- ✅ **Right**: Test expects `decode_packet()` to return a dict, but it returns a tuple. Fix `decode_packet()` to return a dict as designed.

- ❌ **Wrong**: Test fails because field order doesn't match. Reorder the test assertions to match current output.
- ✅ **Right**: Investigate whether the field order is correct per the protocol specification, then fix whichever is wrong (code or test).

- ❌ **Wrong**: Server sends unexpected bytes. Change decoder to silently skip them.
- ✅ **Right**: Check server source code to understand the bytes, then ask whether this is expected behavior or a bug to work around.

## Async Programming Requirements

**All network I/O operations in this project MUST use async/await patterns.**

### Guidelines

1. **Function Signatures**: Any function that performs I/O (network, file, etc.) MUST be defined as `async def`
2. **Awaiting Calls**: Always use `await` when calling async functions
3. **Network Writes**: After `writer.write()`, always call `await writer.drain()` to ensure data is sent
4. **Timeout Handling**: Use `asyncio.wait_for(operation(), timeout=seconds)` and catch `asyncio.TimeoutError`
5. **Error Handling**: Catch `asyncio.IncompleteReadError` when reading from streams
6. **Connection Cleanup**: Always close writers with `writer.close()` followed by `await writer.wait_closed()`
7. **Entry Point**: Only call `asyncio.run()` once at the top-level entry point (fc_ai.py)

### Example Patterns

```python
# Reading from network
async def read_data(reader: asyncio.StreamReader) -> bytes:
    data = await reader.readexactly(num_bytes)
    return data

# Writing to network
async def send_data(writer: asyncio.StreamWriter, data: bytes):
    writer.write(data)
    await writer.drain()

# Timeout handling
try:
    result = await asyncio.wait_for(operation(), timeout=10.0)
except asyncio.TimeoutError:
    print("Operation timed out")
```

## Event-Driven Architecture

The client uses an event-driven architecture with async packet processing:

### Main Event Loop

The main loop follows this sequence:
1. **Connect**: Establish TCP connection to FreeCiv server
2. **Start Reader Task**: Launch `_packet_reader_loop()` as a background asyncio task
3. **Join Game**: Send JOIN_REQ packet and wait for JOIN_REPLY
4. **Wait for Shutdown**: Block until SIGINT/SIGTERM received or connection lost
5. **Disconnect**: Clean up resources and close connection

### Signal Handling

The client registers handlers for graceful shutdown:
- `SIGINT` (Ctrl+C): Sets `shutdown_event` to trigger clean disconnect
- `SIGTERM`: Sets `shutdown_event` to trigger clean disconnect

Signal handlers use `asyncio.create_task()` to set the event from signal context safely.

### Packet Reader Loop

The `_packet_reader_loop()` runs continuously in the background:
1. Read packet header to determine type and length
2. Read packet body based on length
3. Look up handler function for packet type in `self.packet_handlers` dict
4. Call handler with packet data and client context
5. Repeat until connection closed or error occurs

### Handler Registration

Packet handlers are registered at client initialization:

```python
self.packet_handlers = {
    0: handle_processing_started,
    1: handle_processing_finished,
    5: handle_server_join_reply,
    25: handle_server_info,
    29: handle_chat_msg,
}
```

All handlers follow this signature:
```python
async def handle_packet_name(client: FreeCivClient, game_state: GameState, payload: bytes) -> None:
    # Decode packet from payload
    # Update game_state with decoded information
    # Perform any side effects (logging, etc.)
```

**Handler Parameters**:
- `client`: The FreeCivClient instance (provides access to connection, delta cache, etc.)
- `game_state`: The GameState instance to update with packet information
- `payload`: Raw packet body bytes (after packet header has been removed)

### Protocol Version Switching

The client starts with 1-byte packet type numbers for capability negotiation:
- Packets 0-255 use 1-byte type field
- After receiving JOIN_REPLY (packet 5), switches to 2-byte type field
- This allows access to full packet range (0-65535)

The switch happens in `handle_server_join_reply()`:
```python
client.protocol_version = 2  # Switch to 2-byte packet types
```

### Graceful Shutdown

On shutdown signal or connection loss:
1. `shutdown_event.set()` signals main loop to exit
2. Main loop calls `disconnect()`
3. `disconnect()` cancels reader task if still running
4. Close network writer and wait for closure
5. Clear delta cache to maintain consistency

## Delta Protocol

The project implements FreeCiv's delta protocol for bandwidth optimization. This protocol reduces network traffic by 60-90% by transmitting only changed fields in frequently-sent packets.

**For comprehensive technical documentation, see [DELTA_PROTOCOL.md](DELTA_PROTOCOL.md).**

The detailed documentation covers:
- Complete encoding/decoding algorithms with pseudocode
- Bitvector representation and byte ordering (little-endian)
- Cache structure and lifecycle management
- Boolean header folding optimization
- Packet specification flags reference
- Common pitfalls and edge cases with solutions
- Testing strategies and example test cases

### Critical Implementation Notes

**Bitvector Byte Order:**
- FreeCiv uses **little-endian** bit order within each byte
- Bits 0-7 are in byte 0, bits 8-15 are in byte 1, etc.
- Always use `byteorder='little'` when converting bitvector bytes to integers

```python
# CORRECT: Little-endian byte order
bitvector = int.from_bytes(bitvector_bytes, byteorder='little')

# WRONG: Big-endian will decode fields incorrectly
bitvector = int.from_bytes(bitvector_bytes, byteorder='big')
```

**Key Fields:**
- Always transmitted before the bitvector (never included in bitvector)
- Used for cache lookup: `(packet_type, key_tuple)`
- Non-key fields use delta encoding based on bitvector

**Boolean Header Folding:**
- BOOL field values are stored directly in bitvector bits
- No payload bytes are consumed for BOOL fields
- Provides 8x compression for boolean fields

```python
# For BOOL fields, bitvector bit IS the field value
if field_spec.is_bool:
    fields[field_spec.name] = is_bit_set(bitvector, bit_index)
    # No offset increment - no payload bytes consumed
```

**Cache Structure:**
```python
# Cache keyed by (packet_type, key_tuple)
cache = {
    (31, (42,)): {  # City with id=42
        'tile': 1234,
        'owner': 2,
        'size': 5,
        # ... other fields
    }
}
```

### Quick Reference

When implementing delta protocol handlers:

1. Read all key fields first (always present)
2. Read bitvector (size = `ceil(num_non_key_fields / 8)` bytes)
3. Retrieve cached packet or use field defaults
4. For each non-key field:
   - If BOOL: use bitvector bit value directly
   - Elif bit set: read new value from payload
   - Else: use cached value
5. Update cache with complete decoded packet

See [DELTA_PROTOCOL.md](DELTA_PROTOCOL.md) for detailed algorithms, examples, and testing strategies.

### Array-Diff Optimization

**⚠️ IMPORTANT: Our client does NOT currently implement array-diff optimization! ⚠️**

For array fields marked with the "diff" flag in packets.def, FreeCiv uses array-diff encoding to transmit only changed array elements. This optimization is **independent of delta protocol** and works within delta-encoded fields.

**Format:**

Array-diff encodes changed elements as index-value pairs followed by a sentinel:

```
[index₀] [value₀] [index₁] [value₁] ... [array_size_sentinel]
```

**Rules:**

1. **Index is uint8**: Maximum array size is 255 elements
2. **Only changed elements transmitted**: Compared to cached values
3. **Sentinel value equals array size**: For array size 10, sentinel is 10
4. **Protocol error if index > array_size**: Invalid packet
5. **Independent of delta protocol**: Works within both delta and non-delta packets

**Decoding Algorithm:**

```python
def decode_array_diff(payload, offset, array_size, element_decoder, cached_array=None):
    """Decode array-diff encoded field.

    Args:
        payload: Raw packet bytes
        offset: Current read position
        array_size: Fixed size of the array
        element_decoder: Function to decode single element from bytes
        cached_array: Previously received array values (if any)

    Returns:
        (decoded_array, new_offset)
    """
    # Start with cached values or create empty array
    result = list(cached_array) if cached_array else [None] * array_size

    while True:
        # Read index (uint8)
        index = payload[offset]
        offset += 1

        # Check for sentinel (end marker)
        if index == array_size:
            break  # Done reading changes

        # Protocol error check
        if index > array_size:
            raise ValueError(f"Invalid array-diff index {index} > {array_size}")

        # Read value at this index
        value, offset = element_decoder(payload, offset)
        result[index] = value

    return result, offset
```

**Encoding Example:**

For an array of size 10 where elements 2, 5, and 7 changed:

```
Original:  [a, b, c, d, e, f, g, h, i, j]
Changes:   [_, _, X, _, _, Y, _, Z, _, _]

Encoded:   [2] [X] [5] [Y] [7] [Z] [10]
           ^^^ ^^^ ^^^ ^^^ ^^^ ^^^ ^^^^
           idx val idx val idx val sentinel
```

**Real-World Example:**

PACKET_RULESET_GAME uses array-diff for veteran level names:

```python
# packets.def shows: veteran_name[veteran_levels](diff)
# This means veteran_name array uses diff encoding

# For 4 veteran levels, might transmit:
# [0]["green"][1]["veteran"][2]["hardened"][3]["elite"][4]
#  ^    ^      ^     ^        ^      ^       ^    ^     ^
#  idx  val    idx   val      idx    val     idx  val   sentinel=4
```

**Detection:**

In packets.def, array fields marked with `(diff)` use this encoding:

```
veteran_name[veteran_levels](diff)
                             ^^^^^
```

**Implementation Requirements:**

1. Parse packets.def or examine generated C code to identify diff arrays
2. Implement array-diff decoder for each field type (string, uint16, etc.)
3. Maintain cache of previous array values for diff comparison
4. Handle sentinel value correctly (equals array size, NOT max index)

**Testing Strategy:**

```python
# Test with real captured packet bytes
def test_array_diff_veteran_names():
    # Captured from packets/inbound_*_type141.packet
    payload = bytes.fromhex("00 67 72 65 65 6e 00 01 76 65 74 65 72 61 6e 00 02 ...")

    offset = 0
    array_size = 4  # From veteran_levels field

    result, new_offset = decode_array_diff(
        payload, offset, array_size,
        element_decoder=decode_string,  # Each element is a null-terminated string
        cached_array=None
    )

    assert result == ["green", "veteran", "hardened", "elite"]
    assert payload[new_offset-1] == 4  # Sentinel value
```

**Implementation References:**
- Encoding logic: `freeciv/common/generate_packets.py:1273-1351`
- Decoding logic: `freeciv/common/generate_packets.py:1390-1441`
- Documentation: `freeciv/doc/README.delta` lines 23-29
- Generated C code: Search for `DIO_BV_GET` in `packets_gen.c`

**Current Status:**
- ❌ Not implemented in our client
- 🔍 Required for packets with diff-marked arrays (PACKET_RULESET_GAME, etc.)
- 📝 Must be implemented before handling complex ruleset packets

## Packet Debugging

The client includes an optional packet capture utility for debugging protocol issues.

### Enabling Debug Mode

Pass the `--debug-packets` flag when starting the client:
```bash
python3 fc_ai.py --debug-packets
```

This captures all inbound and outbound packets to individual files.

### File Naming Convention

Packets are saved with a structured naming format: `DIRECTION_INDEX_typeNNN.packet`

- **DIRECTION**: `inbound` (from server) or `outbound` (to server)
- **INDEX**: 4-digit zero-padded counter (0001, 0002, 0003, ...)
- **typeNNN**: 3-digit zero-padded packet type number (e.g., type005 for PACKET_SERVER_JOIN_REPLY)

**Examples:**
- `inbound_0001_type005.packet` - First inbound packet, type 5 (SERVER_JOIN_REPLY)
- `inbound_0002_type025.packet` - Second inbound packet, type 25 (SERVER_INFO)
- `outbound_0001_type004.packet` - First outbound packet, type 4 (SERVER_JOIN_REQ)

This naming convention provides:
- **Chronological ordering**: The index shows the order packets were sent/received
- **Quick identification**: The type number lets you identify packet types without inspecting the file
- **Easy filtering**: You can use shell globs to find all packets of a specific type (e.g., `inbound_*_type025.packet`)

Each file contains the raw binary packet data as transmitted/received, including the packet header.

### Use Cases

The packet debugger is valuable for:

**Protocol Development:**
- **Implementing new packet handlers**: Capture real server packets to understand their structure
- **Debugging decoding errors**: Save problematic packets for offline analysis
- **Writing unit tests**: Use captured packets as test fixtures with known-good data
- **Protocol analysis**: Examine exact byte sequences to verify encoding/decoding logic

**Troubleshooting:**
- **Bug reproduction**: Capture the exact sequence of packets that trigger an error
- **State debugging**: Analyze packet history to understand game state changes
- **Delta protocol verification**: Compare packets to ensure delta encoding/decoding is correct
- **Version compatibility**: Compare packets between different server versions

**Development Workflow:**
When implementing a new packet handler (e.g., PACKET_CITY_INFO):
1. Run the client with `--debug-packets` and join a game
2. Find captured packets for the type you're implementing (e.g., `inbound_*_type031.packet`)
3. Use the captured bytes as test fixtures in unit tests
4. Decode the packet structure by examining the raw bytes
5. Implement and test the handler against real server data

### Safety Mechanism

The debugger uses `FileExistsError` prevention:
- If a numbered file already exists, it raises an error rather than overwriting
- This prevents accidental data loss from multiple runs
- Clear old packet files before starting a new debug session

## Network Protocol Notes

- FreeCiv uses a custom binary protocol over TCP
- Server connection defaults to port 6556
- Packets numbered 0-255 are used for initial protocol/capability negotiation
- Capability checking uses special packets that should never change their numbers:
  - PACKET_PROCESSING_STARTED (0)
  - PACKET_PROCESSING_FINISHED (1)
  - PACKET_SERVER_JOIN_REQ (4)
  - PACKET_SERVER_JOIN_REPLY (5)

### Protocol Version Switching

The client dynamically switches packet type field size:
- **Version 1**: Uses 1-byte packet type field (0-255) during capability negotiation
- **Version 2**: Switches to 2-byte packet type field (0-65535) after successful JOIN_REPLY
- This allows initial negotiation with stable packet numbers while supporting full protocol range

**Complete Packet Header Formats:**

FreeCiv uses different header formats depending on protocol version and packet size:

**Initial Protocol (packets 0-255, before JOIN_REPLY):**
```
[uint16 length] [uint8 type] = 3 bytes total header
```

**Normal Protocol (after JOIN_REPLY, packets 0-65535):**
```
[uint16 length] [uint16 type] = 4 bytes total header
```

**Compressed Packet Headers:**
```
Normal compressed: [uint16 (length+16385)] = 2 bytes (no type field - contains multiple packets)
Jumbo compressed:  [uint16 (65535)] [uint32 actual_length] = 6 bytes (for packets > 48KB)
```

**Constants:**
- `COMPRESSION_BORDER = 16*1024 + 1 = 16385`
- `JUMBO_SIZE = 0xffff = 65535`
- `JUMBO_BORDER = 64*1024 - COMPRESSION_BORDER - 1 = 49150`

**Source:** `freeciv/doc/HACKING` lines 183-195, `freeciv/common/networking/packets.c:58,53,63`

### Packet Compression System

**⚠️ CRITICAL: Our client does NOT currently implement packet compression! ⚠️**

FreeCiv uses DEFLATE compression to bundle multiple packets together, reducing network traffic by 60-90%. This system can cause parsing failures if not properly handled.

**How Compression Works:**

1. Server sends `PACKET_FREEZE_CLIENT` (130) to start compression grouping
2. Multiple packets are queued and compressed together using zlib DEFLATE
3. Compressed data sent as a single "packet" with special header
4. Server sends `PACKET_THAW_CLIENT` (131) to end compression grouping

**Compression Detection Logic:**

```python
# Read first 2 bytes as uint16 length field
length = struct.unpack('<H', header_bytes[:2])[0]

if length == 65535:  # JUMBO_SIZE
    # Read next 4 bytes as uint32 actual_length
    # This is a "jumbo" compressed packet (for sizes > 48KB)
    # Total header: 6 bytes
    actual_length = struct.unpack('<I', next_4_bytes)[0]
    compressed_data = reader.readexactly(actual_length)

elif length >= 16385:  # COMPRESSION_BORDER
    # This is a "normal" compressed packet
    # actual_length = length - COMPRESSION_BORDER
    # Total header: 2 bytes
    actual_length = length - 16385
    compressed_data = reader.readexactly(actual_length)

else:
    # Uncompressed packet (length < 16385)
    # Read packet type and continue normal processing
```

**Decompression Process:**

```python
import zlib

# Decompress the data
decompressed = zlib.decompress(compressed_data)

# Decompressed buffer contains multiple packets concatenated
# Must recursively parse each packet from the buffer:
offset = 0
while offset < len(decompressed):
    # Read packet header at current offset
    packet_length = struct.unpack('<H', decompressed[offset:offset+2])[0]
    packet_type = struct.unpack('<H', decompressed[offset+2:offset+4])[0]

    # Extract packet payload
    packet_payload = decompressed[offset+4:offset+packet_length]

    # Process packet with appropriate handler
    handle_packet(packet_type, packet_payload)

    # Move to next packet
    offset += packet_length
```

**PACKET_FREEZE_CLIENT / PACKET_THAW_CLIENT:**

These packets (types 130 and 131) serve dual purposes:

1. **Compression Control:**
   - FREEZE_CLIENT signals the start of a compression group
   - Server queues packets between FREEZE and THAW
   - Sends queued packets as a single compressed unit
   - THAW_CLIENT signals the end of compression

2. **GUI Update Batching:**
   - Clients should defer GUI updates during FREEZE/THAW bracket
   - Prevents flickering from rapid successive updates
   - Used for: game start, player reconnect, end-of-turn processing

**When Compression is Used:**

Servers compress packets during:
- **Game start**: Entire world state (rulesets, map, cities, units)
- **End of turn**: All unit movements, city updates, combat results
- **Reconnect**: Full game state synchronization
- **Large games**: More players, cities, units = more compression

**Why We Haven't Hit This Yet:**

- Server compression is optional (controlled by `FREECIV_COMPRESSION_LEVEL` environment variable)
- Small test games may not trigger compression threshold (~16KB)
- Our testing has been limited to minimal scenarios
- Real games with multiple players and entities will trigger compression

**Impact on Implementation:**

- **Current status**: Compressed packets will cause parsing failures
- **Required work**: Implement zlib decompression in `protocol.py`
- **Testing**: Use `--debug-packets` with real servers to capture compressed packets
- **Priority**: HIGH - Required for production use with real FreeCiv servers

**Implementation References:**
- Server implementation: `freeciv/common/networking/packets.c:442-504`
- Documentation: `freeciv/doc/README.delta` lines 42-74
- Constants: `freeciv/common/networking/packets.c:58,53,63`

### Delta Protocol Implementation

The client implements delta protocol for bandwidth optimization:
- Packets can be sent with only changed fields (indicated by bitvector)
- Cache stores previous values keyed by (packet_type, key_value)
- Decoder reconstructs full packet by combining new and cached fields
- Currently implemented for SERVER_INFO (25) and CHAT_MSG (29)

**Critical Implementation Details:**

For comprehensive technical documentation, see [DELTA_PROTOCOL.md](DELTA_PROTOCOL.md).

**Field Transmission Order:**
Delta packets are transmitted in this specific order (confirmed in `generate_packets.py` lines 2267-2282):
1. **Bitvector** (ceil(non_key_fields / 8) bytes) - indicates which non-key fields are present
2. **Key fields** (always present, transmitted after bitvector)
3. **Non-key fields** (conditional, based on bitvector bits)

Example: `[3 bytes bitvector] [2 bytes nation_id] [conditional fields...]`

**Boolean Header Folding:**
Standalone BOOL fields use an optimization where:
- The bitvector bit IS the field value (True if set, False if clear)
- NO payload bytes are consumed for standalone BOOL fields
- Provides 8x compression for boolean data
- BOOL arrays still transmit each element as a byte in the payload

**Common Pitfalls:**
1. Reading key fields before bitvector (incorrect - bitvector comes first)
2. Reading payload bytes for standalone BOOL fields (incorrect - use bitvector bit)
3. Using big-endian for bitvector (incorrect - FreeCiv uses little-endian)

### Handler Registration Pattern

Packet handlers are registered in a dictionary mapping packet type to handler function:
```python
self.packet_handlers = {
    0: handle_processing_started,
    1: handle_processing_finished,
    5: handle_server_join_reply,
    25: handle_server_info,
    29: handle_chat_msg,
}
```

Handlers receive packet data and client instance, allowing them to update game state and trigger actions.

### Currently Implemented Packet Types

- **0** (PROCESSING_STARTED): Capability negotiation start marker
- **1** (PROCESSING_FINISHED): Capability negotiation end marker
- **5** (SERVER_JOIN_REPLY): Response to join request, triggers protocol version switch
- **25** (SERVER_INFO): Server metadata (turn, year, phase, etc.) with delta support
- **29** (CHAT_MSG): Chat messages from server/players with delta support

Approximately 515 additional packet types remain to be implemented. While packets.def lists packet type numbers and names, the actual structure of each packet MUST be verified from captured packets and generated C code.

### Protocol Implementation Best Practices

**⚠️ CRITICAL: NEVER trust packets.def as your primary source! ⚠️**

**When implementing a new packet decoder:**

**⚠️ IMPORTANT: Test with both compressed and uncompressed packets! ⚠️**

1. **ALWAYS start with captured packets:**
   - Enable packet debugger: `python3 fc_ai.py --debug-packets`
   - Capture real server packets in `packets/` directory
   - Examine raw bytes: `xxd packets/inbound_*_typeNNN.packet`
   - This is your GROUND TRUTH - the actual bytes the server sends
   - **Example:** PACKET_RULESET_GAME (141) packets.def was completely wrong - captured packet showed different structure

2. **Examine generated C code:**
   - Search `freeciv/common/packets_gen.c` for `send_packet_<name>` function
   - This shows the EXACT encoding order and field types
   - Look for `dio_put_uint8`, `dio_put_uint16`, `dio_put_string`, etc.
   - Example: `grep -A 100 "send_packet_ruleset_game" freeciv/common/packets_gen.c`

3. **Consult generate_packets.py for encoding rules:**
   - Understand delta protocol: `freeciv/common/generate_packets.py` lines 2267-2282
   - Boolean header folding: lines 1590-1730
   - Array encoding: lines 1241-1387
   - This explains HOW the generator creates the C code

4. **Use packets.def ONLY as a last resort:**
   - ⚠️ packets.def is a specification, NOT the implementation
   - It may be outdated, wrong, or conditionally compiled differently
   - Use ONLY for: packet numbers, type name mappings (TECH=UINT16, etc.)
   - NEVER trust field order or field presence without verification
   - Example failures: PACKET_RULESET_GAME fields completely wrong

5. **Create test fixtures from captured data:**
   ```python
   # ALWAYS use real captured packet bytes for tests
   # From packets/inbound_0123_type141.packet
   REAL_PACKET = bytes.fromhex("f8 3f 01 17 04 67 72 65 65 6e 00...")

   result = decode_packet_ruleset_game(REAL_PACKET)
   # Verify against what you see in the hex dump
   assert result['veteran_levels'] == 4  # Byte 4 = 0x04
   assert result['veteran_name'][0] == 'green'  # Bytes 5-10
   ```

6. **Debugging workflow:**
   ```bash
   # 1. Capture packets
   python3 fc_ai.py --debug-packets

   # 2. Find the packet type you're implementing
   ls packets/*_type141.packet

   # 3. Examine the hex dump
   xxd packets/inbound_0050_type141.packet | less

   # 4. Compare multiple packets to find patterns
   for f in packets/*_type141.packet; do
       echo "=== $f ==="
       xxd $f | head -5
   done

   # 5. Look at generated C code
   grep -A 50 "send_packet_ruleset_game" freeciv/common/packets_gen.c
   ```

7. **Validate against FreeCiv source:**
   - Use the `freeciv-research` agent to examine server code
   - Compare your Python implementation against C send/receive functions
   - Check `freeciv/server/*.c` for how the server populates packet fields
   - Check for version-specific behavior, conditional compilation

**Ground truth hierarchy (from most to least authoritative):**
1. ✅ **Actual server packets** (captured with --debug-packets) - ULTIMATE TRUTH
2. ✅ **Generated C code** (`packets_gen.c`) - What the server actually runs
3. ✅ **Code generator** (`generate_packets.py`) - Encoding rules and logic
4. ⚠️ **packets.def** - Specification that may not match reality - USE WITH EXTREME CAUTION

**Real-world example of packets.def failure:**
- PACKET_RULESET_GAME (141) packets.def shows: default_specialist, global_init_techs_count, global_init_techs[], global_init_buildings_count, global_init_buildings[], then veteran fields
- Actual packet from FreeCiv 3.2.2: 4 unknown bytes, then veteran fields directly
- Result: 100% of the specification was wrong for this packet
- Solution: Captured real packet, decoded manually, found actual structure

**Compression-Related Testing:**

8. **Test packet handlers with compressed data:**
   - Real servers send compressed packets during game start, end of turn, and reconnect
   - Enable packet debugger and join a real game to capture compressed packets
   - If client fails during bulk updates, suspect compression issues
   - Look for packet length values >= 16385 (COMPRESSION_BORDER) in hex dumps

9. **Scenarios that trigger compression:**
   - **Game start**: Server sends entire world state (map, cities, units, rulesets)
   - **End of turn**: Server sends all unit movements, city updates, combat results
   - **Reconnect**: Server sends full game state to reconnecting client
   - **Large games**: More players/cities/units = more likely to compress

10. **Identifying compressed packets in hex dumps:**
    ```bash
    # Look for length field >= 16385 (0x4001)
    xxd packets/inbound_0050_type000.packet | head -1
    # If first 2 bytes are >= 0x01 0x40, packet is compressed

    # Look for JUMBO packets (length = 65535 = 0xffff)
    xxd packets/inbound_0050_type000.packet | head -1
    # If first 2 bytes are 0xff 0xff, this is a jumbo compressed packet
    ```

11. **Array-diff detection:**
    - Check packets.def for fields marked with `(diff)` flag
    - Example: `veteran_name[veteran_levels](diff)`
    - If implementing a packet with diff arrays, ensure array-diff decoder is used
    - Test with multiple packets to verify only changed elements are transmitted

## Agent Guidance

This section provides guidance for specialized Claude Code agents that work with the FreeCiv AI client codebase. These instructions should be incorporated into agent system prompts.

### freeciv-research Agent

**Purpose:** Research FreeCiv open source project architecture, implementation details, and protocol features.

**Enhanced Knowledge Base:**

The freeciv-research agent should be aware of these critical FreeCiv protocol features:

1. **Packet Compression System:**
   - Implementation: `freeciv/common/networking/packets.c:442-504`
   - Uses zlib DEFLATE compression for packets > 16KB
   - Controlled by PACKET_FREEZE_CLIENT (130) and PACKET_THAW_CLIENT (131)
   - Constants: COMPRESSION_BORDER=16385, JUMBO_SIZE=65535, JUMBO_BORDER=49150
   - Documentation: `freeciv/doc/README.delta` lines 42-74
   - **Critical**: Our client does NOT implement compression yet

2. **Array-Diff Optimization:**
   - Implementation: `freeciv/common/generate_packets.py:1273-1441`
   - Encoding format: [index₀][value₀][index₁][value₁]...[array_size_sentinel]
   - Used for array fields marked with `(diff)` flag in packets.def
   - Documentation: `freeciv/doc/README.delta` lines 23-29
   - Independent of delta protocol (works within delta-encoded fields)

3. **Key Documentation Files:**
   - `freeciv/doc/README.delta` - Delta protocol, compression, and array-diff specifications
   - `freeciv/doc/HACKING` - Protocol details, packet headers, network architecture
   - `freeciv/common/networking/packets.c` - Core packet handling and compression implementation
   - `freeciv/common/networking/packets.def` - Packet specifications (UNRELIABLE - verify with generated code)
   - `freeciv/common/packets_gen.c` - Generated send/receive functions (AUTHORITATIVE)
   - `freeciv/common/packets_gen.h` - Generated packet structures
   - `freeciv/common/generate_packets.py` - Packet code generator with delta/array-diff logic

4. **Protocol Ground Truth Hierarchy:**
   - **Most authoritative**: Captured packets from real FreeCiv server
   - **Highly authoritative**: Generated C code in `packets_gen.c`
   - **Authoritative**: Code generator logic in `generate_packets.py`
   - **UNRELIABLE**: packets.def specification (often wrong or incomplete)

5. **Common Research Tasks:**
   - When asked about packet structure: Check `packets_gen.c` first, NOT packets.def
   - When asked about encoding rules: Examine `generate_packets.py` logic
   - When asked about compression: Reference `packets.c:442-504` and `README.delta:42-74`
   - When asked about delta protocol: Reference `generate_packets.py:2267-2282` for field order
   - When asked about boolean folding: Reference `generate_packets.py:1590-1730`

6. **Search Patterns:**
   ```bash
   # Find packet send function
   grep -A 100 "send_packet_<name>" freeciv/common/packets_gen.c

   # Find packet receive function
   grep -A 100 "receive_packet_<name>" freeciv/common/packets_gen.c

   # Find compression implementation
   grep -A 50 "compress_packet" freeciv/common/networking/packets.c

   # Find array-diff encoding
   grep -A 30 "DIO_BV_PUT" freeciv/common/generate_packets.py
   ```

### packet-handler-builder Agent

**Purpose:** Implement FreeCiv packet handlers for the AI client following project patterns.

**Enhanced Implementation Guidance:**

The packet-handler-builder agent should incorporate these implementation requirements:

1. **Array-Diff Awareness:**
   - Some array fields use "diff" flag in packets.def (e.g., `veteran_name[veteran_levels](diff)`)
   - These fields transmit as: [index₀][value₀][index₁][value₁]...[array_size_sentinel]
   - Sentinel value equals array size (NOT max index)
   - Must loop reading [index][value] pairs until index == array_size
   - Check generated C code for `DIO_BV_GET` calls to identify diff arrays
   - Example: PACKET_RULESET_GAME uses array-diff for veteran_name array

2. **Compression Transparency:**
   - Packet handlers receive decompressed payload (compression handled at protocol layer)
   - Handlers don't need compression logic, but should be aware of PACKET_FREEZE_CLIENT (130) and PACKET_THAW_CLIENT (131)
   - These packets bracket compressed packet groups
   - Test handlers with real server packets captured during game start / end of turn

3. **Header Format Awareness:**
   - Handlers receive payload bytes AFTER packet header has been parsed
   - Delta packets: payload = [bitvector][key fields][non-key fields]
   - Non-delta packets: payload = [all fields in order]
   - Never assume header is included in handler payload

4. **Testing with Compression:**
   - Real FreeCiv servers send compressed packets during:
     - Game start (ruleset/map transmission)
     - End of turn (bulk unit/city updates)
     - Reconnect (full state sync)
   - Use `--debug-packets` to capture real server packets for testing
   - Compression groups multiple packets together, so handlers may be called in bursts
   - Test fixtures should use real captured packet bytes, not synthetic data

5. **Reference Implementation Lookup:**
   - ALWAYS check `freeciv/common/packets_gen.c` for `receive_packet_<name>()` functions
   - This shows EXACT field order and decoding logic (authoritative)
   - Look for `dio_get_uint8`, `dio_get_uint16`, `dio_get_string`, `dio_get_bool8`, etc.
   - Field order in generated C code is the ONLY reliable source
   - NEVER trust packets.def field order without verification

6. **Array-Diff Decoding Pattern:**
   ```python
   def decode_diff_array(payload, offset, array_size, element_decoder):
       """Decode array-diff encoded field.

       Returns: (decoded_array, new_offset)
       """
       result = [None] * array_size

       while True:
           index = payload[offset]
           offset += 1

           if index == array_size:
               break  # Sentinel reached

           if index > array_size:
               raise ValueError(f"Invalid diff index {index}")

           value, offset = element_decoder(payload, offset)
           result[index] = value

       return result, offset
   ```

7. **Common Pitfalls to Avoid:**
   - ❌ Reading key fields before bitvector (bitvector comes first)
   - ❌ Reading payload bytes for standalone BOOL fields (use bitvector bit)
   - ❌ Using big-endian for bitvector (FreeCiv uses little-endian)
   - ❌ Trusting packets.def field order (verify with generated C code)
   - ❌ Forgetting sentinel value for array-diff (sentinel = array_size)
   - ❌ Creating synthetic test data (use real captured packets)

8. **Implementation Checklist:**
   - [ ] Captured real server packet with `--debug-packets`
   - [ ] Examined generated C code in `packets_gen.c`
   - [ ] Identified delta vs non-delta packet
   - [ ] Identified key fields (if delta packet)
   - [ ] Checked for array-diff fields (search for `(diff)` in packets.def)
   - [ ] Implemented field decoder following C code order
   - [ ] Created test fixture from captured packet bytes
   - [ ] Verified test passes with real packet data
   - [ ] Updated packet_specs.py with PacketSpec
   - [ ] Registered handler in client.py packet_handlers dict

### Implementation Notes for Agent Developers

**Location of Agent Definitions:**

Agent instructions are typically defined in:
- Claude Code system configuration files
- `.clinerules` files in the project directory
- Task tool agent type definitions

**Updating Agent Instructions:**

If you cannot directly edit agent system prompts:
1. Document the required changes in this section of CLAUDE.md
2. Notify the user that agent instructions should be updated
3. Provide the specific text to add to each agent's system prompt
4. Reference this section when invoking agents for consistent guidance

**Testing Agent Behavior:**

After updating agent instructions:
1. Test freeciv-research agent with questions about compression and array-diff
2. Test packet-handler-builder agent with implementing a diff-array packet
3. Verify agents reference correct documentation files
4. Confirm agents prioritize generated C code over packets.def

**Example Agent Invocations:**

```python
# Test freeciv-research agent
Task(
    subagent_type="freeciv-research",
    prompt="How does FreeCiv implement packet compression? Show me the C code."
)
# Should reference packets.c:442-504 and explain DEFLATE compression

# Test packet-handler-builder agent
Task(
    subagent_type="packet-handler-builder",
    prompt="Implement handler for PACKET_RULESET_GAME (141) with array-diff support"
)
# Should capture packets, check packets_gen.c, implement array-diff decoding
```
