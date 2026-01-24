from typing import TYPE_CHECKING
from fc_client.game_state import GameState

if TYPE_CHECKING:
    from fc_client.client import FreeCivClient

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

__all__ = [
    "handle_processing_started",
    "handle_processing_finished",
]