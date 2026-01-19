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
  - **protocol.py**: Protocol encoding/decoding functions
    - `async read_packet()`: Reads packets from `asyncio.StreamReader`
    - `async _recv_exact()`: Ensures exact number of bytes are read using `reader.readexactly()`
    - Synchronous encoding functions: `encode_packet()`, `encode_server_join_req()`, etc.
    - Synchronous decoding functions: `decode_server_join_reply()`, etc.

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
3. ✅ Basic packet encoding/decoding for JOIN_REQ and JOIN_REPLY packets
4. ✅ Successful game join with username "ai-user"
5. ✅ Timeout handling for network operations
6. ✅ Graceful connection cleanup

**To Do:**
1. **Protocol Implementation**: Implement encoding/decoding for all packet types defined in `packets.def`
2. **Game State Management**: Track game state, players, cities, units, etc.
3. **AI Strategy**: Implement AI decision-making logic for game actions
4. **Turn Management**: Handle turn-based game loop

## Dependencies

**Runtime Dependencies:**
- Python 3.7+ (for `asyncio` support)
- No external packages required - uses Python standard library

**Development/Testing:**
- Consider `pytest-asyncio` for testing async functions

## Async Programming Requirements

**CRITICAL: All I/O operations in this project MUST use async/await patterns.**

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

## Network Protocol Notes

- FreeCiv uses a custom binary protocol over TCP
- Server connection defaults to port 6556
- Packets numbered 0-255 are used for initial protocol/capability negotiation
- Capability checking uses special packets that should never change their numbers:
  - PACKET_PROCESSING_STARTED
  - PACKET_PROCESSING_FINISHED
  - PACKET_SERVER_JOIN_REQ
  - PACKET_SERVER_JOIN_REPLY
