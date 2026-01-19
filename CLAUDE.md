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

### Core Components

- **fc_ai.py**: Entry point script that initializes and runs the FreeCiv AI client
  - Creates a `FreeCivClient` instance
  - Connects to a FreeCiv server
  - Joins the game as "ai-user"
  - Handles connection lifecycle

- **fc_client/**: Package containing the FreeCiv client implementation
  - **client.py**: Core `FreeCivClient` class that manages TCP socket connections to FreeCiv servers
    - `connect()`: Establishes TCP connection to server
    - `disconnect()`: Closes connection
    - `join_game()`:

### FreeCiv Protocol

- **freeciv/common/networking/packets.def**: Large protocol definition file (2477 lines) from the FreeCiv project
  - Defines all network packet types used in FreeCiv client-server communication
  - Contains packet structure definitions with type mappings (BOOL, UINT8, STRING, etc.)
  - Packet numbers range from 0-520 (with 256-511 reserved for freeciv-web)
  - Includes metadata about packet flags (is-info, is-game-info, force, etc.)
  - This file is typically used to generate protocol handling code

### Current State

This is an early-stage project with basic TCP connectivity established. Key areas that need implementation:

1. **Protocol Implementation**: The `packets.def` file defines the FreeCiv protocol but no parsing/generation code exists yet
2. **Packet Handling**: Need to implement packet serialization/deserialization based on packets.def
3. **Game Logic**: The `join_game()` method is currently incomplete
4. **AI Strategy**: No AI decision-making logic has been implemented

## Dependencies

None so far.

## Network Protocol Notes

- FreeCiv uses a custom binary protocol over TCP
- Server connection defaults to port 6556
- Packets numbered 0-255 are used for initial protocol/capability negotiation
- Capability checking uses special packets that should never change their numbers:
  - PACKET_PROCESSING_STARTED
  - PACKET_PROCESSING_FINISHED
  - PACKET_SERVER_JOIN_REQ
  - PACKET_SERVER_JOIN_REPLY
