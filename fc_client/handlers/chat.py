from typing_extensions import TYPE_CHECKING

from fc_client import protocol
from fc_client.game_state import GameState


if TYPE_CHECKING:
    from fc_client.client import FreeCivClient

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

__all__ = [
    "handle_chat_msg"
]