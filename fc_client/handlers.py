"""
Packet handler functions for the FreeCiv client.

Each handler is an async function that processes a specific packet type.
Handlers receive the client instance and the packet payload, and are
responsible for decoding the payload and updating client state as needed.
"""

from typing import TYPE_CHECKING
from . import protocol

if TYPE_CHECKING:
    from .client import FreeCivClient


async def handle_processing_started(client: 'FreeCivClient', payload: bytes) -> None:
    """
    Handle PACKET_PROCESSING_STARTED.

    This packet indicates the server is starting to process something.
    No payload to decode.
    """
    print("Received PROCESSING_STARTED packet")


async def handle_processing_finished(client: 'FreeCivClient', payload: bytes) -> None:
    """
    Handle PACKET_PROCESSING_FINISHED.

    This packet indicates the server has finished processing.
    No payload to decode.
    """
    print("Received PROCESSING_FINISHED packet")


async def handle_server_join_reply(client: 'FreeCivClient', payload: bytes) -> None:
    """
    Handle PACKET_SERVER_JOIN_REPLY.

    This packet contains the server's response to our join request.
    If successful, set the join_successful event. Otherwise, trigger shutdown.
    """
    # Decode the join reply payload
    data = protocol.decode_server_join_reply(payload)

    if data['you_can_join']:
        print(f"Join successful: {data['message']}")
        # Signal that join was successful
        client._join_successful.set()
    else:
        print(f"Join failed: {data['message']}")
        # Trigger shutdown on join failure
        client._shutdown_event.set()


async def handle_unknown_packet(client: 'FreeCivClient', packet_type: int, payload: bytes) -> None:
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
