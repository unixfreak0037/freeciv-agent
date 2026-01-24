from typing import TYPE_CHECKING

from fc_client import protocol
from fc_client.game_state import GameState

if TYPE_CHECKING:
    from fc_client.client import FreeCivClient

async def handle_server_info(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_SERVER_INFO.

    Uses delta protocol to decode server version information.
    Updates game_state.server_info with server version information.
    """
    # Decode using delta protocol
    packet_spec = protocol.PACKET_SPECS[protocol.PACKET_SERVER_INFO]
    server_info = protocol.decode_delta_packet(payload, packet_spec, client._delta_cache)

    game_state.server_info = server_info

    print(f"Server version: {server_info['version_label']} "
          f"({server_info['major_version']}.{server_info['minor_version']}."
          f"{server_info['patch_version']}-{server_info['emerg_version']})")


async def handle_game_info(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_GAME_INFO (16) - comprehensive game state information.

    This packet uses delta protocol and contains array-diff fields:
    - global_advances[A_LAST]: Boolean array of discovered technologies
    - great_wonder_owners[B_LAST]: Player IDs owning each wonder

    Array-diff optimization transmits only changed array elements as (index, value) pairs.

    Updates game_state.game_info with decoded packet data.
    """
    from ..packet_specs import PACKET_SPECS

    # Decode using delta protocol (handles array-diff automatically)
    spec = PACKET_SPECS[16]
    data = protocol.decode_delta_packet(payload, spec, client._delta_cache)

    # Store in game state
    game_state.game_info = data

    # Display array-diff fields for verification
    global_advances = data.get('global_advances', [])
    great_wonder_owners = data.get('great_wonder_owners', [])
    global_advance_count = data.get('global_advance_count', 0)

    # Count discovered techs
    discovered_count = sum(1 for advance in global_advances if advance) if global_advances else 0

    # Count wonders owned
    owned_wonders = sum(1 for owner in great_wonder_owners if owner >= 0) if great_wonder_owners else 0

    print(f"\n[GAME_INFO] Packet received")
    print(f"  Global advances: {discovered_count}/{len(global_advances)} discovered (count field: {global_advance_count})")
    print(f"  Great wonders: {owned_wonders}/{len(great_wonder_owners)} owned")

__all__ = [
    "handle_server_info",
    "handle_game_info",
]