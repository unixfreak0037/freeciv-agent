from typing import TYPE_CHECKING

from fc_client import protocol
from fc_client.game_state import GameState, RulesetControl

if TYPE_CHECKING:
    from fc_client.client import FreeCivClient

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
    from ..game_state import NationSet

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
    from ..game_state import NationGroup

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
    from ..game_state import Nation

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


async def handle_ruleset_game(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_GAME (141) - core game configuration.

    This packet transmits core ruleset game settings including:
    - Default specialist configuration
    - Global starting techs and buildings (given to all civilizations)
    - Veteran system configuration (levels, names, bonuses, advancement chances)
    - Background color for UI rendering

    Updates game_state.ruleset_game with the complete game configuration.
    """
    from ..game_state import RulesetGame

    # Decode packet
    data = protocol.decode_ruleset_game(payload)

    # Create RulesetGame object
    ruleset_game = RulesetGame(
        default_specialist=data['default_specialist'],
        global_init_techs_count=data['global_init_techs_count'],
        global_init_techs=data['global_init_techs'],
        global_init_buildings_count=data['global_init_buildings_count'],
        global_init_buildings=data['global_init_buildings'],
        veteran_levels=data['veteran_levels'],
        veteran_name=data['veteran_name'],
        power_fact=data['power_fact'],
        move_bonus=data['move_bonus'],
        base_raise_chance=data['base_raise_chance'],
        work_raise_chance=data['work_raise_chance'],
        background_red=data['background_red'],
        background_green=data['background_green'],
        background_blue=data['background_blue'],
    )

    # Store in game state
    game_state.ruleset_game = ruleset_game

    # Display summary
    print(f"\n[RULESET GAME] Game Configuration")
    print(f"  Default Specialist: {ruleset_game.default_specialist}")
    print(f"  Global Starting Techs: {ruleset_game.global_init_techs_count} "
          f"(IDs: {ruleset_game.global_init_techs})")
    print(f"  Global Starting Buildings: {ruleset_game.global_init_buildings_count} "
          f"(IDs: {ruleset_game.global_init_buildings})")
    print(f"  Background Color: RGB({ruleset_game.background_red}, "
          f"{ruleset_game.background_green}, {ruleset_game.background_blue})")

    # Display veteran system
    print(f"\n  Veteran System: {ruleset_game.veteran_levels} levels")
    for i in range(ruleset_game.veteran_levels):
        print(f"    {i}: {ruleset_game.veteran_name[i]} - "
              f"Power: {ruleset_game.power_fact[i]}, "
              f"Move: {ruleset_game.move_bonus[i]}, "
              f"Base: {ruleset_game.base_raise_chance[i]}%, "
              f"Work: {ruleset_game.work_raise_chance[i]}%")


async def handle_ruleset_disaster(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_DISASTER (224) - disaster type configuration.

    Disasters are negative random events (fires, plagues, etc.) that can occur
    in cities when requirements are met. One packet is sent per disaster type
    during game initialization.

    Updates game_state.disasters dict with the disaster type configuration.
    """
    from ..game_state import DisasterType, Requirement

    # Decode packet
    data = protocol.decode_ruleset_disaster(payload)

    # Convert requirements to Requirement objects
    requirements = [
        Requirement(
            type=req['type'],
            value=req['value'],
            range=req['range'],
            survives=req['survives'],
            present=req['present'],
            quiet=req['quiet']
        )
        for req in data['reqs']
    ]

    # Create DisasterType object
    disaster = DisasterType(
        id=data['id'],
        name=data['name'],
        rule_name=data['rule_name'],
        reqs_count=data['reqs_count'],
        reqs=requirements,
        frequency=data['frequency'],
        effects=data['effects']
    )

    # Store in game state
    game_state.disasters[disaster.id] = disaster

    # Decode effects bitvector for display
    effect_names = []
    effect_mapping = {
        0: "DestroyBuilding",
        1: "ReducePopulation",
        2: "EmptyFoodStock",
        3: "EmptyProdStock",
        4: "Pollution",
        5: "Fallout",
        6: "ReducePopDestroy"
    }

    for bit in range(7):
        if data['effects'] & (1 << bit):
            effect_names.append(effect_mapping[bit])

    effects_str = ", ".join(effect_names) if effect_names else "none"

    # Display summary
    print(f"\n[DISASTER {disaster.id}] {disaster.name} ({disaster.rule_name})")
    print(f"  Frequency: {disaster.frequency}")
    print(f"  Requirements: {disaster.reqs_count}")
    print(f"  Effects: {effects_str}")

__all__ = [
    "handle_ruleset_control",
    "handle_ruleset_summary",
    "handle_ruleset_description_part",
    "handle_ruleset_nation_sets",
    "handle_ruleset_nation_groups",
    "handle_ruleset_nation",
    "handle_nation_availability",
    "handle_ruleset_game",
    "handle_ruleset_disaster",
]