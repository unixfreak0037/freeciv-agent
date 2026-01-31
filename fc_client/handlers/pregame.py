from typing import TYPE_CHECKING

from fc_client import protocol
from fc_client.game_state import GameState

if TYPE_CHECKING:
    from fc_client.client import FreeCivClient


async def handle_server_join_reply(
    client: "FreeCivClient", game_state: GameState, payload: bytes
) -> None:
    """
    Handle PACKET_SERVER_JOIN_REPLY.

    This packet contains the server's response to our join request.
    If successful, set the join_successful event. Otherwise, trigger shutdown.
    """
    # Decode the join reply payload
    data = protocol.decode_server_join_reply(payload)

    if data["you_can_join"]:
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


__all__ = [
    "handle_server_join_reply",
]
