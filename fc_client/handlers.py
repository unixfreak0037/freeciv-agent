"""
Packet handler functions for the FreeCiv client.

Each handler is an async function that processes a specific packet type.
Handlers receive the client instance and the packet payload, and are
responsible for decoding the payload and updating client state as needed.
"""

from typing import TYPE_CHECKING
from . import protocol
from .game_state import GameState, RulesetControl

if TYPE_CHECKING:
    from .client import FreeCivClient


async def handle_processing_started(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_PROCESSING_STARTED.

    This packet indicates the server is starting to process something.
    No payload to decode.
    """
    print("Received PROCESSING_STARTED packet")


async def handle_processing_finished(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_PROCESSING_FINISHED.

    This packet indicates the server has finished processing.
    No payload to decode.
    """
    print("Received PROCESSING_FINISHED packet")


async def handle_server_join_reply(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_SERVER_JOIN_REPLY.

    This packet contains the server's response to our join request.
    If successful, set the join_successful event. Otherwise, trigger shutdown.
    """
    # Decode the join reply payload
    data = protocol.decode_server_join_reply(payload)

    if data['you_can_join']:
        print(f"Join successful: {data['message']}")

        # CRITICAL: Switch to 2-byte packet type format after successful join
        # The FreeCiv protocol switches from UINT8 to UINT16 packet types after JOIN_REPLY
        client._use_two_byte_type = True

        # Signal that join was successful
        client._join_successful.set()
    else:
        print(f"Join failed: {data['message']}")
        # Trigger shutdown on join failure
        client._shutdown_event.set()


async def handle_server_info(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_SERVER_INFO.

    Updates game_state.server_info with server version information.
    """
    server_info = protocol.decode_server_info(payload)
    game_state.server_info = server_info

    print(f"Server version: {server_info['version_label']} "
          f"({server_info['major_version']}.{server_info['minor_version']}."
          f"{server_info['patch_version']}-{server_info['emerg_version']})")


async def handle_chat_msg(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_CHAT_MSG.

    Decodes chat message using delta protocol, stores in game state with timestamp,
    and displays to console.
    """
    from datetime import datetime

    # Decode packet using delta protocol
    packet_spec = protocol.PACKET_SPECS[protocol.PACKET_CHAT_MSG]
    data = protocol.decode_delta_packet(payload, packet_spec, client._delta_cache)

    # Create history entry with timestamp
    timestamp = datetime.now().isoformat()
    history_entry = {
        'timestamp': timestamp,
        'message': data['message'],
        'tile': data['tile'],
        'event': data['event'],
        'turn': data['turn'],
        'phase': data['phase'],
        'conn_id': data['conn_id']
    }

    # Store in game state
    game_state.chat_history.append(history_entry)

    # Display to console
    time_str = datetime.fromisoformat(timestamp).strftime('%H:%M:%S')
    print(f"\n[CHAT {time_str}] {data['message']}")
    print(f"  Turn: {data['turn']} | Phase: {data['phase']} | "
          f"Event: {data['event']} | Tile: {data['tile']} | Conn: {data['conn_id']}")


async def handle_ruleset_control(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_CONTROL.

    This packet contains ruleset configuration including counts of all game entities
    (units, techs, nations, etc.) and metadata. Sent during initialization to inform
    the client what to expect from subsequent ruleset data packets.

    Updates game_state.ruleset_control with complete ruleset configuration.
    """
    # Decode using delta protocol (returns dict)
    packet_spec = protocol.PACKET_SPECS[protocol.PACKET_RULESET_CONTROL]
    data = protocol.decode_delta_packet(payload, packet_spec, client._delta_cache)

    # Convert dict to typed dataclass
    ruleset = RulesetControl(**data)

    # Store in game state
    game_state.ruleset_control = ruleset

    # Display summary (using attribute access)
    print(f"\n[RULESET] {ruleset.name} v{ruleset.version}")
    print(f"  Units: {ruleset.num_unit_types} ({ruleset.num_unit_classes} classes)")
    print(f"  Techs: {ruleset.num_tech_types} ({ruleset.num_tech_classes} classes)")
    print(f"  Nations: {ruleset.nation_count} ({ruleset.num_nation_groups} groups)")
    print(f"  Improvements: {ruleset.num_impr_types}")
    print(f"  Terrain: {ruleset.terrain_count}")
    print(f"  Governments: {ruleset.government_count}")


async def handle_ruleset_summary(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_SUMMARY.

    This packet contains a summary text describing the ruleset.
    Sent during game initialization to provide overview information.

    Updates game_state.ruleset_summary with the text content.
    """
    # Decode packet (simple, non-delta)
    data = protocol.decode_ruleset_summary(payload)

    # Store in game state
    game_state.ruleset_summary = data['text']

    # Display summary (truncate if very long)
    text = data['text']
    if len(text) > 200:
        preview = text[:200] + "..."
    else:
        preview = text

    print(f"\n[RULESET SUMMARY]")
    print(preview)


async def handle_unknown_packet(client: 'FreeCivClient', game_state: GameState, packet_type: int, payload: bytes) -> None:
    """
    Handle unknown/unimplemented packet types.

    This handler logs detailed information about the packet and triggers
    shutdown to force incremental implementation of packet handlers.
    """
    print(f"\n!!! UNKNOWN PACKET RECEIVED !!!")
    print(f"Packet Type: {packet_type}")
    print(f"Payload Length: {len(payload)} bytes")

    # Hex dump first 64 bytes
    dump_size = min(64, len(payload))
    hex_dump = ' '.join(f'{b:02x}' for b in payload[:dump_size])
    print(f"First {dump_size} bytes: {hex_dump}")

    print(f"\n>>> Need to implement handler for packet type {packet_type}")
    print(">>> Stopping application...\n")

    # Trigger shutdown
    client._shutdown_event.set()
