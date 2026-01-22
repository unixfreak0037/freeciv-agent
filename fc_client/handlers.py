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

    # Reset description accumulator for new ruleset
    game_state.ruleset_description_parts = []
    game_state.ruleset_description = None

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


async def handle_ruleset_description_part(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_DESCRIPTION_PART.

    This packet contains one chunk of the ruleset description text.
    Multiple parts are sent after RULESET_CONTROL and must be accumulated
    until total bytes >= desc_length from ruleset_control.

    Multi-part assembly algorithm:
    1. Decode the text chunk from payload
    2. Append to game_state.ruleset_description_parts
    3. Calculate total accumulated bytes (UTF-8 encoding)
    4. If total >= expected desc_length:
       - Join all parts into complete description
       - Store in game_state.ruleset_description
       - Clear accumulator for next ruleset load

    Updates game_state.ruleset_description_parts (accumulator) and
    game_state.ruleset_description (final assembled text).
    """
    # Decode packet (simple, non-delta)
    data = protocol.decode_ruleset_description_part(payload)
    chunk_text = data['text']

    # Append chunk to accumulator
    game_state.ruleset_description_parts.append(chunk_text)

    # Calculate total bytes accumulated (UTF-8 encoding, not character count)
    total_bytes = sum(len(part.encode('utf-8')) for part in game_state.ruleset_description_parts)

    # Check if we have expected desc_length from RULESET_CONTROL
    if game_state.ruleset_control is None:
        print(f"\n[WARNING] Received RULESET_DESCRIPTION_PART before RULESET_CONTROL")
        print(f"  Accumulated {len(game_state.ruleset_description_parts)} part(s), {total_bytes} bytes")
        return

    expected_length = game_state.ruleset_control.desc_length

    # Print progress
    progress_pct = min(100, int(100 * total_bytes / expected_length)) if expected_length > 0 else 0
    print(f"[RULESET DESC] Part {len(game_state.ruleset_description_parts)}: "
          f"{len(chunk_text)} bytes (total: {total_bytes}/{expected_length} bytes, {progress_pct}%)")

    # Check if assembly is complete
    if total_bytes >= expected_length:
        # Join all parts into complete description
        complete_description = ''.join(game_state.ruleset_description_parts)
        game_state.ruleset_description = complete_description

        # Clear accumulator
        game_state.ruleset_description_parts = []

        # Display completion message
        print(f"\n[RULESET DESCRIPTION] Assembly complete: {len(complete_description)} characters")

        # Show preview (first 300 chars)
        if len(complete_description) > 300:
            preview = complete_description[:300] + "..."
        else:
            preview = complete_description

        print(preview)
        print()  # Blank line for readability


async def handle_ruleset_nation_sets(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_NATION_SETS.

    This packet contains the list of available nation sets (collections of nations
    grouped by theme, era, or region). Sent during game initialization.

    Updates game_state.nation_sets with list of NationSet objects.
    """
    from .game_state import NationSet

    # Decode packet
    data = protocol.decode_ruleset_nation_sets(payload)

    # Transform parallel arrays into list of objects
    nation_sets = []
    for i in range(data['nsets']):
        nation_set = NationSet(
            name=data['names'][i],
            rule_name=data['rule_names'][i],
            description=data['descriptions'][i]
        )
        nation_sets.append(nation_set)

    # Store in game state (replaces previous data)
    game_state.nation_sets = nation_sets

    # Display summary
    print(f"\n[NATION SETS] {len(nation_sets)} available")
    for nation_set in nation_sets:
        # Truncate long descriptions for console output
        desc_preview = (nation_set.description[:60] + "..."
                       if len(nation_set.description) > 60
                       else nation_set.description)
        print(f"  - {nation_set.name} ({nation_set.rule_name})")
        if desc_preview:
            print(f"    {desc_preview}")


async def handle_ruleset_nation_groups(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_NATION_GROUPS.

    This packet contains the list of available nation groups (categories of nations
    such as "Ancient", "Medieval", "African", "European", etc.). Groups can be
    hidden from player selection. Sent during game initialization.

    Updates game_state.nation_groups with list of NationGroup objects.
    """
    from .game_state import NationGroup

    # Decode packet
    data = protocol.decode_ruleset_nation_groups(payload)

    # Transform parallel arrays into list of objects
    nation_groups = []
    for i in range(data['ngroups']):
        nation_group = NationGroup(
            name=data['groups'][i],
            hidden=data['hidden'][i]
        )
        nation_groups.append(nation_group)

    # Store in game state (replaces previous data)
    game_state.nation_groups = nation_groups

    # Display summary
    print(f"\n[NATION GROUPS] {len(nation_groups)} available")
    for nation_group in nation_groups:
        visibility = "hidden" if nation_group.hidden else "visible"
        print(f"  - {nation_group.name} ({visibility})")


async def handle_ruleset_nation(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_NATION (148) - nation/civilization data.

    This packet contains detailed information about a single nation, including
    leaders, starting conditions (government, techs, units, buildings), and
    membership in nation sets and groups. One packet is sent per nation during
    game initialization.

    Updates game_state.nations dict with Nation objects keyed by nation ID.
    """
    from .game_state import Nation

    # Decode packet using manual decoder
    data = protocol.decode_ruleset_nation(payload)

    # Create Nation object from decoded data
    nation = Nation(
        id=data['id'],
        translation_domain=data.get('translation_domain', ''),
        adjective=data.get('adjective', ''),
        rule_name=data.get('rule_name', ''),
        noun_plural=data.get('noun_plural', ''),
        graphic_str=data.get('graphic_str', ''),
        graphic_alt=data.get('graphic_alt', ''),
        legend=data.get('legend', ''),
        style=data.get('style', 0),
        leader_count=data.get('leader_count', 0),
        leader_name=data.get('leader_name', []),
        leader_is_male=data.get('leader_is_male', []),
        is_playable=data.get('is_playable', False),
        barbarian_type=data.get('barbarian_type', 0),
        nsets=data.get('nsets', 0),
        sets=data.get('sets', []),
        ngroups=data.get('ngroups', 0),
        groups=data.get('groups', []),
        init_government_id=data.get('init_government_id', -1),
        init_techs_count=data.get('init_techs_count', 0),
        init_techs=data.get('init_techs', []),
        init_units_count=data.get('init_units_count', 0),
        init_units=data.get('init_units', []),
        init_buildings_count=data.get('init_buildings_count', 0),
        init_buildings=data.get('init_buildings', [])
    )

    # Store in game state by nation ID
    game_state.nations[nation.id] = nation

    # Display summary
    leaders_str = ", ".join(nation.leader_name[:3])
    if len(nation.leader_name) > 3:
        leaders_str += f", +{len(nation.leader_name) - 3} more"

    playable = "playable" if nation.is_playable else "not playable"

    print(f"\n[NATION {nation.id}] {nation.adjective} ({nation.rule_name})")
    print(f"  Leaders: {leaders_str}")
    print(f"  Status: {playable}")
    print(f"  Sets: {len(nation.sets)}, Groups: {len(nation.groups)}")
    print(f"  Starting: {nation.init_techs_count} techs, "
          f"{nation.init_units_count} units, {nation.init_buildings_count} buildings")


async def handle_nation_availability(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_NATION_AVAILABILITY (237).

    This packet indicates which nations are available for player selection.
    Sent when nation availability changes (e.g., another player picks a nation,
    or the nation set changes).

    Updates game_state.nation_availability with current availability data.
    """
    # Decode packet (simple, non-delta)
    data = protocol.decode_nation_availability(payload)

    # Store in game state
    game_state.nation_availability = {
        'ncount': data['ncount'],
        'is_pickable': data['is_pickable'],
        'nationset_change': data['nationset_change']
    }

    # Display summary
    available_count = sum(data['is_pickable'])
    total_count = data['ncount']

    print(f"\n[NATION AVAILABILITY] {available_count}/{total_count} nations available")
    if data['nationset_change']:
        print("  Nation set changed")

    # Display detailed availability (limit to first 10 for brevity)
    if game_state.nations:
        print("  Available nations:")
        shown = 0
        for nation_id, is_available in enumerate(data['is_pickable']):
            if is_available and nation_id in game_state.nations:
                nation = game_state.nations[nation_id]
                print(f"    - {nation.adjective} ({nation.rule_name})")
                shown += 1
                if shown >= 10:
                    remaining = available_count - shown
                    if remaining > 0:
                        print(f"    ... and {remaining} more")
                    break


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
