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
    - Saves inbound/outbound packets to numbered files

### FreeCiv Protocol

- **freeciv/common/networking/packets.def**: Large protocol definition file (2477 lines) from the FreeCiv project
  - Defines all network packet types used in FreeCiv client-server communication
  - Contains packet structure definitions with type mappings (BOOL, UINT8, STRING, etc.)
  - Packet numbers range from 0-520 (with 256-511 reserved for freeciv-web)
  - Includes metadata about packet flags (is-info, is-game-info, force, etc.)
  - This file is typically used to generate protocol handling code

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
1. **Protocol Implementation**: Implement encoding/decoding for remaining ~515 packet types defined in `packets.def`
2. **Game State Management**: Expand tracking to include players, cities, units, map tiles, etc.
3. **AI Strategy**: Implement AI decision-making logic for game actions
4. **Turn Management**: Handle turn-based game loop and action submission
5. **Action Encoding**: Implement packet encoding for player actions (move unit, build, etc.)

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

FreeCiv uses a delta protocol to reduce bandwidth by only transmitting changed fields in frequently-sent packets.

### How It Works

Instead of sending all fields every time, the server:
1. **Sends a bitvector** indicating which fields are present in this packet
2. **Includes only the present fields** in the packet body
3. **Client reconstructs** full packet by combining new fields with cached values

### Bitvectors

A bitvector is a compact bit array where each bit represents one field:
- Bit set to 1: Field is present in packet, read new value
- Bit set to 0: Field is absent, use cached value from previous packet

Bitvectors are packed into bytes, read with helper functions:
```python
def is_bit_set(bitvector: bytes, bit_index: int) -> bool:
    byte_index = bit_index // 8
    bit_offset = bit_index % 8
    return bool(bitvector[byte_index] & (1 << bit_offset))
```

### Cache Structure

The `DeltaCache` stores previous packet values:
- **Key**: Tuple of `(packet_type, key_value)`
  - `packet_type`: Which packet type (e.g., 25 for SERVER_INFO)
  - `key_value`: Unique identifier for this specific instance (e.g., server ID)
- **Value**: Dictionary mapping field names to their last seen values

Example cache entry:
```python
{
    (25, 0): {  # SERVER_INFO for server 0
        'turn': 42,
        'year': 1850,
        'phase': 'Movement',
        # ... other fields
    }
}
```

### Key Fields vs. Non-Key Fields

Packet specifications define one "key" field:
- **Key field**: Always transmitted (even in delta packets), used for cache lookup
- **Non-key fields**: May be omitted using delta protocol

For example, SERVER_INFO uses server ID as the key field.

### Decoding Algorithm

The `decode_delta_packet()` function follows this process:

1. **Read key field**: Extract the key field value (always present)
2. **Read bitvector**: Read N bytes where N = ceil(num_non_key_fields / 8)
3. **Check cache**: Look up previous values using (packet_type, key_value)
4. **Decode fields**: For each non-key field in order:
   - If bit is set: Read new value from packet, update cache
   - If bit is clear: Use cached value from previous packet
5. **Return result**: Combined dictionary of all field values

### Cache Lifecycle

- **Created**: Empty dict when client initializes
- **Updated**: Modified by `decode_delta_packet()` as packets arrive
- **Cleared**: Emptied on disconnect to ensure consistency for next connection

## Packet Debugging

The client includes an optional packet capture utility for debugging protocol issues.

### Enabling Debug Mode

Pass the `--debug-packets` flag when starting the client:
```bash
python3 fc_ai.py --debug-packets
```

This captures all inbound and outbound packets to individual files.

### File Naming Convention

Packets are saved with sequential numbering:
- **Inbound**: `inbound_0.packet`, `inbound_1.packet`, `inbound_2.packet`, ...
- **Outbound**: `outbound_0.packet`, `outbound_1.packet`, `outbound_2.packet`, ...

Each file contains the raw binary packet data as transmitted/received.

### Use Cases

Captured packets are useful for:
- **Protocol analysis**: Examine exact byte sequences sent/received
- **Bug reproduction**: Save packets that trigger errors
- **Comparison testing**: Compare packets from different client/server versions
- **Manual decoding**: Write test decoders against known-good packet data
- **Documentation**: Create examples of real packet structures

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

### Delta Protocol Implementation

The client implements delta protocol for bandwidth optimization:
- Packets can be sent with only changed fields (indicated by bitvector)
- Cache stores previous values keyed by (packet_type, key_value)
- Decoder reconstructs full packet by combining new and cached fields
- Currently implemented for SERVER_INFO (25) and CHAT_MSG (29)

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

Approximately 515 additional packet types remain to be implemented from packets.def.
