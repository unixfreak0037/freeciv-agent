from typing import TYPE_CHECKING

from fc_client import protocol
from fc_client.game_state import GameState, RulesetControl, TerrainControl

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


async def handle_ruleset_specialist(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_SPECIALIST (142) - specialist type definitions.

    Specialists are special citizen types that can work in cities to provide
    bonuses (e.g., scientists produce research, entertainers provide luxury,
    taxmen generate gold) instead of working terrain tiles. Each packet defines
    one specialist type with its properties, requirements, and help text.

    Uses delta protocol with 9 conditional fields. Sent during ruleset
    initialization, one packet per specialist type.

    Updates game_state.specialists dict, keyed by specialist ID.
    """
    from ..game_state import Specialist, Requirement

    # Decode using manual decoder
    data = protocol.decode_ruleset_specialist(payload, client._delta_cache)

    # Convert requirements list
    requirements = [
        Requirement(**req) for req in data.get('reqs', [])
    ]

    # Create typed dataclass
    specialist = Specialist(
        id=data['id'],
        plural_name=data.get('plural_name', ''),
        rule_name=data.get('rule_name', ''),
        short_name=data.get('short_name', ''),
        graphic_str=data.get('graphic_str', ''),
        graphic_alt=data.get('graphic_alt', ''),
        reqs_count=data.get('reqs_count', 0),
        reqs=requirements,
        helptext=data.get('helptext', '')
    )

    # Store in game state
    game_state.specialists[specialist.id] = specialist

    # Display summary
    print(f"\n[SPECIALIST {specialist.id}] {specialist.plural_name} ({specialist.rule_name})")
    print(f"  Short Name: {specialist.short_name}")
    print(f"  Graphics: {specialist.graphic_str}")
    if specialist.graphic_alt and specialist.graphic_alt != '-':
        print(f"    Alt: {specialist.graphic_alt}")
    if specialist.reqs_count > 0:
        print(f"  Requirements: {specialist.reqs_count}")

    # Display help text (truncated)
    if specialist.helptext:
        help_preview = (specialist.helptext[:100] + '...'
                       if len(specialist.helptext) > 100
                       else specialist.helptext)
        print(f"  Help: {help_preview}")


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


async def handle_ruleset_achievement(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_ACHIEVEMENT (233) - achievement type configuration.

    Achievements are special accomplishments players can earn during the game.
    One packet is sent per achievement type during game initialization.

    Updates game_state.achievements dict with the achievement type configuration.
    """
    from ..game_state import AchievementType

    # Decode packet
    data = protocol.decode_ruleset_achievement(payload)

    # Create AchievementType object
    achievement = AchievementType(
        id=data['id'],
        name=data['name'],
        rule_name=data['rule_name'],
        type=data['type'],
        unique=data['unique']
    )

    # Store in game state
    game_state.achievements[achievement.id] = achievement

    # Map achievement type enum to human-readable names
    type_names = {
        0: "Spaceship", 1: "Map_Known", 2: "Multicultural",
        3: "Cultured_City", 4: "Cultured_Nation", 5: "Lucky",
        6: "Huts", 7: "Metropolis", 8: "Literate", 9: "Land_Ahoy"
    }

    type_str = type_names.get(achievement.type, f"Unknown({achievement.type})")
    unique_str = "unique" if achievement.unique else "repeatable"

    # Display summary
    print(f"\n[ACHIEVEMENT {achievement.id}] {achievement.name} ({achievement.rule_name})")
    print(f"  Type: {type_str}")
    print(f"  Status: {unique_str}")


async def handle_ruleset_trade(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_TRADE (227) - trade route configuration."""
    from ..game_state import TradeRouteType

    # Decode packet
    data = protocol.decode_ruleset_trade(payload)

    # Create TradeRouteType object
    trade_route = TradeRouteType(
        id=data['id'],
        trade_pct=data['trade_pct'],
        cancelling=data['cancelling'],
        bonus_type=data['bonus_type']
    )

    # Store in game state
    game_state.trade_routes[trade_route.id] = trade_route

    # Map enum values for display
    cancelling_names = {0: "Active", 1: "Inactive", 2: "Cancel"}
    bonus_type_names = {0: "None", 1: "Gold", 2: "Science", 3: "Both"}

    cancelling_str = cancelling_names.get(
        trade_route.cancelling, f"Unknown({trade_route.cancelling})"
    )
    bonus_str = bonus_type_names.get(
        trade_route.bonus_type, f"Unknown({trade_route.bonus_type})"
    )

    # Display summary
    print(f"\n[TRADE ROUTE {trade_route.id}]")
    print(f"  Trade Percentage: {trade_route.trade_pct}%")
    print(f"  Illegal Route Handling: {cancelling_str}")
    print(f"  Bonus Type: {bonus_str}")


async def handle_ruleset_resource(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_RESOURCE (177) - resource type configuration.

    Resources provide bonuses to tile outputs (e.g., Gold, Wheat, Horses).
    Each resource defines output bonuses for the 6 output types.

    Updates game_state.resources dict with the resource configuration.
    """
    from ..game_state import Resource

    # Decode packet
    data = protocol.decode_ruleset_resource(payload)

    # Create Resource object
    resource = Resource(
        id=data['id'],
        output=data['output']
    )

    # Store in game state
    game_state.resources[resource.id] = resource

    # Format output bonuses for display (show only non-zero values)
    output_names = ["Food", "Shield", "Trade", "Gold", "Luxury", "Science"]
    bonuses = []
    for i, value in enumerate(resource.output):
        if value > 0:
            bonuses.append(f"{output_names[i]}+{value}")

    bonus_str = ", ".join(bonuses) if bonuses else "No bonuses"
    print(f"[RESOURCE] ID {resource.id}: {bonus_str}")


async def handle_ruleset_action(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_ACTION (246) - action type configuration.

    Actions define what units can do in the game: establish embassies,
    create trade routes, spy missions, combat actions, etc. One packet
    is sent per action type during game initialization.

    Updates game_state.actions dict with the action type configuration.
    """
    from ..game_state import ActionType

    # Decode packet
    data = protocol.decode_ruleset_action(payload)

    # Create ActionType object
    action = ActionType(
        id=data['id'],
        ui_name=data['ui_name'],
        quiet=data['quiet'],
        result=data['result'],
        sub_results=data['sub_results'],
        actor_consuming_always=data['actor_consuming_always'],
        act_kind=data['act_kind'],
        tgt_kind=data['tgt_kind'],
        sub_tgt_kind=data['sub_tgt_kind'],
        min_distance=data['min_distance'],
        max_distance=data['max_distance'],
        blocked_by=data['blocked_by']
    )

    # Store in game state
    game_state.actions[action.id] = action

    # Map enum values for display
    actor_kind_names = {0: "Unit", 1: "Player", 2: "City", 3: "Tile"}
    target_kind_names = {0: "City", 1: "Unit", 2: "Units", 3: "Tile", 4: "Extras", 5: "Self"}

    actor_str = actor_kind_names.get(action.act_kind, f"Unknown({action.act_kind})")
    target_str = target_kind_names.get(action.tgt_kind, f"Unknown({action.tgt_kind})")

    # Display distance constraints
    if action.max_distance == -1:
        distance_str = f"min={action.min_distance}, unlimited"
    else:
        distance_str = f"{action.min_distance}-{action.max_distance}"

    # Count blocking actions
    blocking_count = bin(action.blocked_by).count('1')

    # Display summary
    print(f"\n[ACTION {action.id}] {action.ui_name}")
    print(f"  Actor: {actor_str}, Target: {target_str}")
    print(f"  Distance: {distance_str}")
    print(f"  Consumes actor: {action.actor_consuming_always}")
    print(f"  Blocked by: {blocking_count} actions")
    if action.quiet:
        print(f"  (quiet mode)")


async def handle_ruleset_action_enabler(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_ACTION_ENABLER (235) - action enabler configuration.

    Action enablers define conditions for when game actions can be performed.
    Each enabler specifies requirements for the actor (unit/city/player) and
    target (recipient of action). Multiple enablers can exist for the same action.

    Updates game_state.action_enablers list by appending each new enabler.
    """
    from ..game_state import ActionEnabler, Requirement

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_action_enabler(payload, client._delta_cache)

    # Convert actor requirements to Requirement objects
    actor_requirements = [
        Requirement(
            type=req['type'],
            value=req['value'],
            range=req['range'],
            survives=req['survives'],
            present=req['present'],
            quiet=req['quiet']
        )
        for req in data['actor_reqs']
    ]

    # Convert target requirements to Requirement objects
    target_requirements = [
        Requirement(
            type=req['type'],
            value=req['value'],
            range=req['range'],
            survives=req['survives'],
            present=req['present'],
            quiet=req['quiet']
        )
        for req in data['target_reqs']
    ]

    # Create ActionEnabler object
    enabler = ActionEnabler(
        enabled_action=data['enabled_action'],
        actor_reqs_count=data['actor_reqs_count'],
        actor_reqs=actor_requirements,
        target_reqs_count=data['target_reqs_count'],
        target_reqs=target_requirements
    )

    # Append to game state (multiple enablers can exist for same action)
    game_state.action_enablers.append(enabler)

    # Look up action name (if action has been received already)
    action_name = "Unknown"
    if enabler.enabled_action in game_state.actions:
        action_name = game_state.actions[enabler.enabled_action].ui_name

    # Display summary
    print(f"\n[ACTION ENABLER] Action {enabler.enabled_action} ({action_name})")
    print(f"  Actor requirements: {enabler.actor_reqs_count}")
    print(f"  Target requirements: {enabler.target_reqs_count}")

    # If requirement count is small (<=3), show detailed view
    if enabler.actor_reqs_count <= 3 and enabler.actor_reqs_count > 0:
        for i, req in enumerate(actor_requirements):
            present_str = "present" if req.present else "absent"
            print(f"    Actor req {i}: type={req.type}, value={req.value}, {present_str}")

    if enabler.target_reqs_count <= 3 and enabler.target_reqs_count > 0:
        for i, req in enumerate(target_requirements):
            present_str = "present" if req.present else "absent"
            print(f"    Target req {i}: type={req.type}, value={req.value}, {present_str}")


async def handle_ruleset_action_auto(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_ACTION_AUTO (252) - automatic action configuration.

    Defines rules for automatically performing actions when specific triggers occur,
    without player input (e.g., disbanding unit on upkeep failure, auto-attack when
    moving adjacent to enemy).

    Updates game_state.action_auto_performers list by appending each new configuration.
    """
    from ..game_state import ActionAutoPerformer, Requirement

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_action_auto(payload, client._delta_cache)

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

    # Create ActionAutoPerformer object
    auto_performer = ActionAutoPerformer(
        id=data['id'],
        cause=data['cause'],
        reqs_count=data['reqs_count'],
        reqs=requirements,
        alternatives_count=data['alternatives_count'],
        alternatives=data['alternatives']
    )

    # Append to game state (multiple auto performers can exist)
    game_state.action_auto_performers.append(auto_performer)

    # Cause enum names for display
    cause_names = {
        0: "UNIT_UPKEEP",
        1: "UNIT_MOVED_ADJ",
        2: "POST_ACTION",
        3: "CITY_GONE",
        4: "UNIT_STACK_DEATH"
    }
    cause_name = cause_names.get(auto_performer.cause, f"UNKNOWN({auto_performer.cause})")

    # Display summary
    print(f"\n[ACTION AUTO] ID {auto_performer.id}, Cause: {cause_name}")
    print(f"  Requirements: {auto_performer.reqs_count}")
    print(f"  Alternative actions: {auto_performer.alternatives_count} - {auto_performer.alternatives}")

    # If requirement count is small (<=3), show detailed view
    if auto_performer.reqs_count <= 3 and auto_performer.reqs_count > 0:
        for i, req in enumerate(requirements):
            present_str = "present" if req.present else "absent"
            print(f"    Req {i}: type={req.type}, value={req.value}, {present_str}")


async def handle_ruleset_tech_flag(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_TECH_FLAG (234).

    Technology flags are properties that can be assigned to technologies
    in the ruleset to define game mechanics and requirements.

    Updates game_state.tech_flags dictionary with the technology flag.
    """
    from ..game_state import TechFlag

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_tech_flag(payload, client._delta_cache)

    # Create TechFlag object
    tech_flag = TechFlag(
        id=data['id'],
        name=data['name'],
        helptxt=data['helptxt']
    )

    # Store in game state (keyed by ID)
    game_state.tech_flags[tech_flag.id] = tech_flag

    # Display summary
    print(f"\n[TECH FLAG {tech_flag.id}] {tech_flag.name}")
    if tech_flag.helptxt:
        # Truncate long help text for console display
        help_preview = tech_flag.helptxt[:100] + '...' if len(tech_flag.helptxt) > 100 else tech_flag.helptxt
        print(f"  Help: {help_preview}")


async def handle_ruleset_extra_flag(client: 'FreeCivClient', game_state: GameState, payload: bytes) -> None:
    """
    Handle PACKET_RULESET_EXTRA_FLAG (226).

    Extra flags are properties that can be assigned to extras (terrain features
    like forests, rivers, bases) in the ruleset to define game mechanics.

    Updates game_state.extra_flags dictionary with the extra flag.
    """
    from ..game_state import ExtraFlag

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_extra_flag(payload, client._delta_cache)

    # Create ExtraFlag object
    extra_flag = ExtraFlag(
        id=data['id'],
        name=data['name'],
        helptxt=data['helptxt']
    )

    # Store in game state (keyed by ID)
    game_state.extra_flags[extra_flag.id] = extra_flag

    # Display summary
    print(f"\n[EXTRA FLAG {extra_flag.id}] {extra_flag.name}")
    if extra_flag.helptxt:
        # Truncate long help text for console display
        help_preview = extra_flag.helptxt[:100] + '...' if len(extra_flag.helptxt) > 100 else extra_flag.helptxt
        print(f"  Help: {help_preview}")


async def handle_ruleset_terrain_flag(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_TERRAIN_FLAG (231).

    Terrain flags are properties that can be assigned to terrain types
    in the ruleset to define game mechanics and requirements.

    Updates game_state.terrain_flags dictionary with the terrain flag.
    """
    from ..game_state import TerrainFlag

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_terrain_flag(payload, client._delta_cache)

    # Create TerrainFlag object
    terrain_flag = TerrainFlag(
        id=data['id'],
        name=data['name'],
        helptxt=data['helptxt']
    )

    # Store in game state (keyed by ID)
    game_state.terrain_flags[terrain_flag.id] = terrain_flag

    # Display summary
    print(f"\n[TERRAIN FLAG {terrain_flag.id}] {terrain_flag.name}")
    if terrain_flag.helptxt:
        # Truncate long help text for console display
        help_preview = terrain_flag.helptxt[:100] + '...' if len(terrain_flag.helptxt) > 100 else terrain_flag.helptxt
        print(f"  Help: {help_preview}")


async def handle_ruleset_unit_class(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_UNIT_CLASS (152) - unit class definition.

    Unit classes define categories of military units (e.g., Land, Sea, Air)
    with shared movement and combat properties. Multiple packets sent during
    ruleset initialization (one per unit class).

    Updates game_state.unit_classes dictionary with the unit class configuration.
    """
    from ..game_state import UnitClass

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_unit_class(payload, client._delta_cache)

    # Create UnitClass object
    unit_class = UnitClass(
        id=data['id'],
        name=data['name'],
        rule_name=data['rule_name'],
        min_speed=data['min_speed'],
        hp_loss_pct=data['hp_loss_pct'],
        non_native_def_pct=data['non_native_def_pct'],
        flags=data['flags'],
        helptext=data['helptext']
    )

    # Store in game state (keyed by ID)
    game_state.unit_classes[unit_class.id] = unit_class

    # Display summary
    print(f"\n[UNIT CLASS {unit_class.id}] {unit_class.name} ({unit_class.rule_name})")
    print(f"  Min Speed: {unit_class.min_speed}")
    print(f"  HP Loss: {unit_class.hp_loss_pct}%")
    print(f"  Non-native Defense: {unit_class.non_native_def_pct}%")
    print(f"  Flags: 0x{unit_class.flags:08x}")

    if unit_class.helptext:
        # Truncate long help text for console display
        help_preview = unit_class.helptext[:100] + '...' if len(unit_class.helptext) > 100 else unit_class.helptext
        print(f"  Help: {help_preview}")


async def handle_ruleset_base(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_BASE (153) - base type definition."""
    from ..game_state import BaseType

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_base(payload, client._delta_cache)

    # Create BaseType object
    base_type = BaseType(
        id=data['id'],
        gui_type=data['gui_type'],
        border_sq=data['border_sq'],
        vision_main_sq=data['vision_main_sq'],
        vision_invis_sq=data['vision_invis_sq'],
        vision_subs_sq=data['vision_subs_sq']
    )

    # Store in game state
    game_state.base_types[base_type.id] = base_type

    # Display summary
    gui_type_names = {0: 'Fortress', 1: 'Airbase', 2: 'Other'}
    gui_name = gui_type_names.get(base_type.gui_type, f'Unknown({base_type.gui_type})')

    print(f"\n[BASE TYPE {base_type.id}] {gui_name}")
    print(f"  Border Expansion: {base_type.border_sq if base_type.border_sq >= 0 else 'None'}")
    print(f"  Vision (Main): {base_type.vision_main_sq if base_type.vision_main_sq >= 0 else 'None'}")
    print(f"  Vision (Invisible): {base_type.vision_invis_sq if base_type.vision_invis_sq >= 0 else 'None'}")
    print(f"  Vision (Submarines): {base_type.vision_subs_sq if base_type.vision_subs_sq >= 0 else 'None'}")


async def handle_ruleset_road(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_ROAD (220) - road type definition."""
    from ..game_state import RoadType, Requirement

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_road(payload, client._delta_cache)

    # Convert requirement dicts to Requirement objects
    first_reqs = [
        Requirement(**req) for req in data['first_reqs']
    ]

    # Create RoadType object
    road_type = RoadType(
        id=data['id'],
        gui_type=data['gui_type'],
        first_reqs_count=data['first_reqs_count'],
        first_reqs=first_reqs,
        move_cost=data['move_cost'],
        move_mode=data['move_mode'],
        tile_incr_const=data['tile_incr_const'],
        tile_incr=data['tile_incr'],
        tile_bonus=data['tile_bonus'],
        compat=data['compat'],
        integrates=data['integrates'],
        flags=data['flags']
    )

    # Store in game state
    game_state.road_types[road_type.id] = road_type

    # Display summary
    gui_type_names = {0: 'Road', 1: 'Railroad', 2: 'Maglev', 3: 'Other'}
    move_mode_names = {0: 'Cardinal', 1: 'Relaxed', 2: 'FastAlways'}
    compat_names = {0: 'Road', 1: 'Railroad', 2: 'River', 3: 'None'}
    output_names = ['Food', 'Shield', 'Trade', 'Gold', 'Luxury', 'Science']
    flag_names = {0: 'River', 1: 'UnrestrictedInfra', 2: 'JumpFrom', 3: 'JumpTo'}

    gui_name = gui_type_names.get(road_type.gui_type, f'Unknown({road_type.gui_type})')
    mode_name = move_mode_names.get(road_type.move_mode, f'Unknown({road_type.move_mode})')
    compat_name = compat_names.get(road_type.compat, f'Unknown({road_type.compat})')

    print(f"\n[ROAD TYPE {road_type.id}] {gui_name}")
    print(f"  Movement: cost={road_type.move_cost}, mode={mode_name}")
    print(f"  Compatibility: {compat_name}")

    # Display tile bonuses (only non-zero values)
    bonuses = []
    for i, (const_val, incr_val, bonus_val) in enumerate(zip(
        road_type.tile_incr_const,
        road_type.tile_incr,
        road_type.tile_bonus
    )):
        if const_val != 0 or incr_val != 0 or bonus_val != 0:
            parts = []
            if const_val != 0:
                parts.append(f"+{const_val}")
            if incr_val != 0:
                parts.append(f"+{incr_val}%")
            if bonus_val != 0:
                parts.append(f"bonus={bonus_val}")
            bonuses.append(f"{output_names[i]}({', '.join(parts)})")

    if bonuses:
        print(f"  Tile bonuses: {', '.join(bonuses)}")

    # Display flags (if any active)
    active_flags = []
    for bit, name in flag_names.items():
        if road_type.flags & (1 << bit):
            active_flags.append(name)
    if active_flags:
        print(f"  Flags: {', '.join(active_flags)}")

    # Display requirements count
    if road_type.first_reqs_count > 0:
        print(f"  Requirements: {road_type.first_reqs_count}")

    # Display integrates count (if non-zero)
    if road_type.integrates != 0:
        # Count set bits
        integrates_count = bin(road_type.integrates).count('1')
        print(f"  Integrates with: {integrates_count} extras")


async def handle_ruleset_goods(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_GOODS (248) - trade goods configuration."""
    from ..game_state import Goods, Requirement

    # Decode packet using delta cache
    data = protocol.decode_ruleset_goods(payload, client._delta_cache)

    # Convert requirement dicts to Requirement objects
    requirements = [Requirement(**req) for req in data.get('reqs', [])]

    # Create Goods object
    goods = Goods(
        id=data['id'],
        name=data['name'],
        rule_name=data['rule_name'],
        reqs_count=data['reqs_count'],
        reqs=requirements,
        from_pct=data['from_pct'],
        to_pct=data['to_pct'],
        onetime_pct=data['onetime_pct'],
        flags=data['flags'],
        helptext=data['helptext']
    )

    # Store in game state
    game_state.goods[goods.id] = goods

    # Display formatted summary
    print(f"\n[GOODS {goods.id}] {goods.name} ({goods.rule_name})")
    print(f"  Trade Percentages: from={goods.from_pct}%, to={goods.to_pct}%, onetime={goods.onetime_pct}%")

    if goods.reqs_count > 0:
        print(f"  Requirements: {goods.reqs_count}")

    if goods.flags != 0:
        flag_names = []
        if goods.flags & 0x01:
            flag_names.append("Bidirectional")
        if goods.flags & 0x02:
            flag_names.append("Depletes")
        if goods.flags & 0x04:
            flag_names.append("Self-Provided")
        print(f"  Flags: {', '.join(flag_names)}")

    if goods.helptext:
        help_preview = (goods.helptext[:100] + '...'
                       if len(goods.helptext) > 100
                       else goods.helptext)
        print(f"  Help: {help_preview}")


async def handle_ruleset_unit_class_flag(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_UNIT_CLASS_FLAG (230) - unit class flag definition.

    Unit class flags are properties that can be assigned to unit classes
    in the ruleset to define game mechanics and requirements.

    Updates game_state.unit_class_flags dictionary with the unit class flag.
    """
    from ..game_state import UnitClassFlag

    # Decode packet with delta cache support
    data = protocol.decode_ruleset_unit_class_flag(payload, client._delta_cache)

    # Create UnitClassFlag object
    unit_class_flag = UnitClassFlag(
        id=data['id'],
        name=data['name'],
        helptxt=data['helptxt']
    )

    # Store in game state (keyed by ID)
    game_state.unit_class_flags[unit_class_flag.id] = unit_class_flag

    # Display summary
    print(f"\n[UNIT CLASS FLAG {unit_class_flag.id}] {unit_class_flag.name}")
    if unit_class_flag.helptxt:
        # Truncate long help text for console display
        help_preview = unit_class_flag.helptxt[:100] + '...' if len(unit_class_flag.helptxt) > 100 else unit_class_flag.helptxt
        print(f"  Help: {help_preview}")


async def handle_ruleset_unit_flag(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_UNIT_FLAG (229) - unit flag definition.

    Unit flags are properties that can be assigned to units
    in the ruleset to define game mechanics and requirements.
    """
    from ..game_state import UnitFlag

    # Decode packet
    data = protocol.decode_ruleset_unit_flag(payload, client._delta_cache)

    # Create UnitFlag object
    unit_flag = UnitFlag(
        id=data['id'],
        name=data['name'],
        helptxt=data['helptxt']
    )

    # Store in game state
    game_state.unit_flags[unit_flag.id] = unit_flag

    # Display summary
    print(f"\n[UNIT FLAG {unit_flag.id}] {unit_flag.name}")
    if unit_flag.helptxt:
        help_preview = unit_flag.helptxt[:100] + '...' if len(unit_flag.helptxt) > 100 else unit_flag.helptxt
        print(f"  Help: {help_preview}")


async def handle_ruleset_unit_bonus(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_UNIT_BONUS (228) - unit combat bonus configuration.

    Defines conditional bonuses that units receive when fighting against enemies
    with specific flags (e.g., Pikemen get +50% defense vs Mounted units).

    Updates game_state.unit_bonuses list by appending each new bonus.
    """
    from ..game_state import UnitBonus

    # Decode packet with delta cache
    data = protocol.decode_ruleset_unit_bonus(payload, client._delta_cache)

    # Create UnitBonus object
    bonus = UnitBonus(
        unit=data['unit'],
        flag=data['flag'],
        type=data['type'],
        value=data['value'],
        quiet=data['quiet']
    )

    # Append to game state (multiple bonuses can exist)
    game_state.unit_bonuses.append(bonus)

    # Map enum values for display
    bonus_type_names = {
        0: "DefenseMultiplier",
        1: "DefenseDivider",
        2: "FirepowerMultiplier",
        3: "FirepowerDivider"
    }

    type_str = bonus_type_names.get(bonus.type, f"Unknown({bonus.type})")
    quiet_str = " (quiet)" if bonus.quiet else ""

    # Look up unit name if available
    unit_name = f"Unit {bonus.unit}"
    if bonus.unit in game_state.unit_types:
        unit_name = game_state.unit_types[bonus.unit].name

    # Look up flag name if available
    flag_name = f"Flag {bonus.flag}"
    if bonus.flag in game_state.unit_flags:
        flag_name = game_state.unit_flags[bonus.flag].name

    # Display summary
    print(f"\n[UNIT BONUS] {unit_name} vs {flag_name}")
    print(f"  Type: {type_str}, Value: {bonus.value}{quiet_str}")


async def handle_ruleset_tech(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_TECH (144) - technology definition.

    Technologies represent scientific advances that players can research.
    Updates game_state.techs dict with technology configuration.
    """
    from ..game_state import Tech, Requirement

    # Decode packet with delta cache
    data = protocol.decode_ruleset_tech(payload, client._delta_cache)

    # Convert research requirements to Requirement objects
    research_requirements = [
        Requirement(
            type=req['type'],
            value=req['value'],
            range=req['range'],
            survives=req['survives'],
            present=req['present'],
            quiet=req['quiet']
        )
        for req in data['research_reqs']
    ]

    # Create Tech object
    tech = Tech(
        id=data['id'],
        root_req=data['root_req'],
        research_reqs_count=data['research_reqs_count'],
        research_reqs=research_requirements,
        tclass=data['tclass'],
        removed=data['removed'],
        flags=data['flags'],
        cost=data['cost'],
        num_reqs=data['num_reqs'],
        name=data['name'],
        rule_name=data['rule_name'],
        helptext=data['helptext'],
        graphic_str=data['graphic_str'],
        graphic_alt=data['graphic_alt']
    )

    # Store in game state
    game_state.techs[tech.id] = tech

    # Display summary
    status = "REMOVED" if tech.removed else "active"
    print(f"\n[TECH {tech.id}] {tech.name} ({tech.rule_name}) - {status}")
    print(f"  Cost: {tech.cost} beakers")
    print(f"  Class: {tech.tclass}")

    if tech.root_req != 0:
        print(f"  Root requirement: Tech {tech.root_req}")

    if tech.research_reqs_count > 0:
        print(f"  Research requirements: {tech.research_reqs_count}")
        if tech.research_reqs_count <= 3:
            for i, req in enumerate(research_requirements):
                present_str = "present" if req.present else "absent"
                print(f"    Req {i}: type={req.type}, value={req.value}, {present_str}")

    if tech.flags != 0:
        flag_count = bin(tech.flags).count('1')
        print(f"  Flags: {flag_count} active (0x{tech.flags:x})")

    if tech.helptext:
        help_preview = tech.helptext[:80] + '...' if len(tech.helptext) > 80 else tech.helptext
        print(f"  Help: {help_preview}")


async def handle_ruleset_government_ruler_title(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_GOVERNMENT_RULER_TITLE (143) - ruler title definition.

    Updates game_state.government_ruler_titles list with ruler titles for
    government/nation combinations.
    """
    from ..game_state import GovernmentRulerTitle

    # Decode packet with delta cache
    data = protocol.decode_ruleset_government_ruler_title(payload, client._delta_cache)

    # Create GovernmentRulerTitle object
    ruler_title = GovernmentRulerTitle(
        gov=data['gov'],
        nation=data['nation'],
        male_title=data['male_title'],
        female_title=data['female_title']
    )

    # Store in game state
    game_state.government_ruler_titles.append(ruler_title)

    # Display summary
    print(f"[RULER TITLE] Gov {ruler_title.gov}, Nation {ruler_title.nation}: "
          f"{ruler_title.male_title}/{ruler_title.female_title}")


async def handle_ruleset_government(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_GOVERNMENT (145) - government type definition.

    Updates game_state.governments dict with government configuration.
    """
    from ..game_state import Government, Requirement

    # Decode packet with delta cache
    data = protocol.decode_ruleset_government(payload, client._delta_cache)

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

    # Create Government object
    government = Government(
        id=data['id'],
        reqs_count=data['reqs_count'],
        reqs=requirements,
        name=data['name'],
        rule_name=data['rule_name'],
        graphic_str=data['graphic_str'],
        graphic_alt=data['graphic_alt'],
        sound_str=data['sound_str'],
        sound_alt=data['sound_alt'],
        sound_alt2=data['sound_alt2'],
        helptext=data['helptext']
    )

    # Store in game state
    game_state.governments[government.id] = government

    # Display summary
    print(f"\n[GOVERNMENT {government.id}] {government.name} ({government.rule_name})")
    print(f"  Graphics: {government.graphic_str}")

    if government.reqs_count > 0:
        print(f"  Requirements: {government.reqs_count}")


async def handle_ruleset_unit(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_UNIT (140) - unit type definition.

    Defines characteristics of military/civilian units (Warrior, Settler, etc.).
    One packet sent per unit type during ruleset initialization.
    """
    from ..game_state import UnitType, Requirement

    # Decode with delta cache
    data = protocol.decode_ruleset_unit(payload, client._delta_cache)

    # Convert requirements dicts to Requirement objects
    requirements = [
        Requirement(
            type=req['type'],
            value=req['value'],
            range=req['range'],
            survives=req['survives'],
            present=req['present'],
            quiet=req['quiet']
        )
        for req in data['build_reqs']
    ]

    # Create UnitType object
    unit_type = UnitType(
        id=data['id'],
        name=data['name'],
        rule_name=data['rule_name'],
        graphic_str=data['graphic_str'],
        graphic_alt=data['graphic_alt'],
        graphic_alt2=data['graphic_alt2'],
        sound_move=data['sound_move'],
        sound_move_alt=data['sound_move_alt'],
        sound_fight=data['sound_fight'],
        sound_fight_alt=data['sound_fight_alt'],
        unit_class_id=data['unit_class_id'],
        build_cost=data['build_cost'],
        pop_cost=data['pop_cost'],
        happy_cost=data['happy_cost'],
        upkeep=data['upkeep'],
        attack_strength=data['attack_strength'],
        defense_strength=data['defense_strength'],
        firepower=data['firepower'],
        hp=data['hp'],
        move_rate=data['move_rate'],
        fuel=data['fuel'],
        build_reqs_count=data['build_reqs_count'],
        build_reqs=requirements,
        vision_radius_sq=data['vision_radius_sq'],
        transport_capacity=data['transport_capacity'],
        cargo=data['cargo'],
        embarks=data['embarks'],
        disembarks=data['disembarks'],
        obsoleted_by=data['obsoleted_by'],
        converted_to=data['converted_to'],
        convert_time=data['convert_time'],
        bombard_rate=data['bombard_rate'],
        paratroopers_range=data['paratroopers_range'],
        city_size=data['city_size'],
        city_slots=data['city_slots'],
        tp_defense=data['tp_defense'],
        targets=data['targets'],
        vlayer=data['vlayer'],
        veteran_levels=data['veteran_levels'],
        veteran_name=data['veteran_name'],
        power_fact=data['power_fact'],
        move_bonus=data['move_bonus'],
        base_raise_chance=data['base_raise_chance'],
        work_raise_chance=data['work_raise_chance'],
        flags=data['flags'],
        roles=data['roles'],
        worker=data['worker'],
        helptext=data['helptext']
    )

    # Store in game state
    game_state.unit_types[unit_type.id] = unit_type

    # Display summary
    print(f"\n[UNIT {unit_type.id}] {unit_type.name} ({unit_type.rule_name})")
    print(f"  Cost: {unit_type.build_cost} shields", end='')
    if unit_type.pop_cost > 0:
        print(f", {unit_type.pop_cost} pop", end='')
    print()

    print(f"  Combat: {unit_type.attack_strength}/{unit_type.defense_strength}/{unit_type.hp} HP", end='')
    if unit_type.firepower > 1:
        print(f", firepower {unit_type.firepower}", end='')
    print()

    print(f"  Movement: {unit_type.move_rate}", end='')
    if unit_type.fuel > 0:
        print(f", fuel {unit_type.fuel}", end='')
    print()

    # Display special abilities
    abilities = []
    if unit_type.worker:
        abilities.append("worker")
    if unit_type.transport_capacity > 0:
        abilities.append(f"transport({unit_type.transport_capacity})")
    if unit_type.bombard_rate > 0:
        abilities.append(f"bombard({unit_type.bombard_rate})")
    if unit_type.paratroopers_range > 0:
        abilities.append(f"paradrop({unit_type.paratroopers_range})")
    if unit_type.city_size > 0:
        abilities.append(f"found_city({unit_type.city_size})")

    if abilities:
        print(f"  Abilities: {', '.join(abilities)}")

    # Display veteran system if present
    if unit_type.veteran_levels > 0:
        print(f"  Veteran levels: {unit_type.veteran_levels}")


async def handle_ruleset_extra(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """
    Handle PACKET_RULESET_EXTRA (232) - extra type definition.

    Extras are terrain features like forests, rivers, roads, bases, and other
    map improvements. This packet defines the properties and behavior of each
    extra type in the ruleset.

    Updates game_state.extras dict with ExtraType objects keyed by extra ID.
    """
    from ..game_state import ExtraType, Requirement

    # Decode packet
    data = protocol.decode_ruleset_extra(payload, client._delta_cache)

    # Convert requirement arrays to Requirement objects
    reqs = [Requirement(**req) for req in data.get('reqs', [])]
    rmreqs = [Requirement(**req) for req in data.get('rmreqs', [])]
    appearance_reqs = [Requirement(**req) for req in data.get('appearance_reqs', [])]
    disappearance_reqs = [Requirement(**req) for req in data.get('disappearance_reqs', [])]

    # Create ExtraType object with all 41 fields
    extra = ExtraType(
        id=data['id'],
        name=data.get('name', ''),
        rule_name=data.get('rule_name', ''),
        category=data.get('category', 0),
        causes=data.get('causes', 0),
        rmcauses=data.get('rmcauses', 0),
        activity_gfx=data.get('activity_gfx', ''),
        act_gfx_alt=data.get('act_gfx_alt', ''),
        act_gfx_alt2=data.get('act_gfx_alt2', ''),
        rmact_gfx=data.get('rmact_gfx', ''),
        rmact_gfx_alt=data.get('rmact_gfx_alt', ''),
        rmact_gfx_alt2=data.get('rmact_gfx_alt2', ''),
        graphic_str=data.get('graphic_str', ''),
        graphic_alt=data.get('graphic_alt', ''),
        reqs_count=data.get('reqs_count', 0),
        reqs=reqs,
        rmreqs_count=data.get('rmreqs_count', 0),
        rmreqs=rmreqs,
        appearance_chance=data.get('appearance_chance', 0),
        appearance_reqs_count=data.get('appearance_reqs_count', 0),
        appearance_reqs=appearance_reqs,
        disappearance_chance=data.get('disappearance_chance', 0),
        disappearance_reqs_count=data.get('disappearance_reqs_count', 0),
        disappearance_reqs=disappearance_reqs,
        visibility_req=data.get('visibility_req', 0),
        buildable=data.get('buildable', False),
        generated=data.get('generated', False),
        build_time=data.get('build_time', 0),
        build_time_factor=data.get('build_time_factor', 0),
        removal_time=data.get('removal_time', 0),
        removal_time_factor=data.get('removal_time_factor', 0),
        infracost=data.get('infracost', 0),
        defense_bonus=data.get('defense_bonus', 0),
        eus=data.get('eus', 0),
        native_to=data.get('native_to', 0),
        flags=data.get('flags', 0),
        hidden_by=data.get('hidden_by', 0),
        bridged_over=data.get('bridged_over', 0),
        conflicts=data.get('conflicts', 0),
        no_aggr_near_city=data.get('no_aggr_near_city', 0),
        helptext=data.get('helptext', '')
    )

    # Store in game state
    game_state.extras[extra.id] = extra

    # Display summary
    print(f"\n[EXTRA {extra.id}] {extra.name} ({extra.rule_name})")
    print(f"  Category: {extra.category}")

    # Display build info
    if extra.buildable:
        build_info = f"buildable"
        if extra.build_time > 0:
            build_info += f", {extra.build_time} turns"
        print(f"  Build: {build_info}")

    # Display removal info
    if extra.removal_time > 0:
        print(f"  Removal: {extra.removal_time} turns")

    # Display special properties
    properties = []
    if extra.generated:
        properties.append("auto-generated")
    if extra.defense_bonus > 0:
        properties.append(f"+{extra.defense_bonus}% defense")
    if extra.infracost > 0:
        properties.append(f"infracost {extra.infracost}")

    if properties:
        print(f"  Properties: {', '.join(properties)}")

    # Display requirements if present
    if extra.reqs_count > 0:
        print(f"  Build requirements: {extra.reqs_count}")


async def handle_ruleset_terrain_control(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_TERRAIN_CONTROL (146) - terrain control settings.

    Contains global terrain mechanics configuration including movement rules,
    channel/reclaim requirements, lake size limits, and GUI type mappings.

    Updates game_state.terrain_control with the configuration.
    """
    # Decode packet
    data = protocol.decode_ruleset_terrain_control(payload, client._delta_cache)

    # Create TerrainControl object
    terrain_control = TerrainControl(
        ocean_reclaim_requirement_pct=data['ocean_reclaim_requirement_pct'],
        land_channel_requirement_pct=data['land_channel_requirement_pct'],
        terrain_thaw_requirement_pct=data['terrain_thaw_requirement_pct'],
        terrain_freeze_requirement_pct=data['terrain_freeze_requirement_pct'],
        lake_max_size=data['lake_max_size'],
        min_start_native_area=data['min_start_native_area'],
        move_fragments=data['move_fragments'],
        igter_cost=data['igter_cost'],
        pythagorean_diagonal=data['pythagorean_diagonal'],
        infrapoints=data['infrapoints'],
        gui_type_base0=data['gui_type_base0'],
        gui_type_base1=data['gui_type_base1']
    )

    # Store in game state
    game_state.terrain_control = terrain_control

    # Display formatted summary
    print("\n[TERRAIN CONTROL]")
    print(f"  Movement: {terrain_control.move_fragments} fragments per move")
    print(f"  Ignore Terrain Cost: {terrain_control.igter_cost}")
    print(f"  Pythagorean Diagonal: {'Yes' if terrain_control.pythagorean_diagonal else 'No'}")
    print(f"  Infrastructure Points: {'Enabled' if terrain_control.infrapoints else 'Disabled'}")
    print(f"  Lake Max Size: {terrain_control.lake_max_size}")
    print(f"  Min Start Native Area: {terrain_control.min_start_native_area}")

    # Display transformation percentages if non-zero
    transformations = []
    if terrain_control.ocean_reclaim_requirement_pct > 0:
        transformations.append(f"Ocean reclaim: {terrain_control.ocean_reclaim_requirement_pct}%")
    if terrain_control.land_channel_requirement_pct > 0:
        transformations.append(f"Land channel: {terrain_control.land_channel_requirement_pct}%")
    if terrain_control.terrain_thaw_requirement_pct > 0:
        transformations.append(f"Terrain thaw: {terrain_control.terrain_thaw_requirement_pct}%")
    if terrain_control.terrain_freeze_requirement_pct > 0:
        transformations.append(f"Terrain freeze: {terrain_control.terrain_freeze_requirement_pct}%")

    if transformations:
        print("  Transformation requirements:")
        for transform in transformations:
            print(f"    - {transform}")

    # Display GUI type bases if set
    gui_types = []
    if terrain_control.gui_type_base0:
        gui_types.append(f"Base 0: {terrain_control.gui_type_base0}")
    if terrain_control.gui_type_base1:
        gui_types.append(f"Base 1: {terrain_control.gui_type_base1}")

    if gui_types:
        print("  GUI Types:")
        for gui_type in gui_types:
            print(f"    - {gui_type}")


async def handle_ruleset_terrain(
    client: 'FreeCivClient',
    game_state: GameState,
    payload: bytes
) -> None:
    """Handle PACKET_RULESET_TERRAIN (151) - terrain type definition."""
    from fc_client.game_state import Terrain

    # Decode packet
    data = protocol.decode_ruleset_terrain(payload, client._delta_cache)

    # Create Terrain object
    terrain = Terrain(
        id=data['id'],
        tclass=data['tclass'],
        flags=data['flags'],
        native_to=data['native_to'],
        name=data['name'],
        rule_name=data['rule_name'],
        graphic_str=data['graphic_str'],
        graphic_alt=data['graphic_alt'],
        graphic_alt2=data['graphic_alt2'],
        movement_cost=data['movement_cost'],
        defense_bonus=data['defense_bonus'],
        output=data['output'],
        num_resources=data['num_resources'],
        resources=data['resources'],
        resource_freq=data['resource_freq'],
        road_output_incr_pct=data['road_output_incr_pct'],
        base_time=data['base_time'],
        road_time=data['road_time'],
        cultivate_result=data['cultivate_result'],
        cultivate_time=data['cultivate_time'],
        plant_result=data['plant_result'],
        plant_time=data['plant_time'],
        irrigation_food_incr=data['irrigation_food_incr'],
        irrigation_time=data['irrigation_time'],
        mining_shield_incr=data['mining_shield_incr'],
        mining_time=data['mining_time'],
        animal=data['animal'],
        transform_result=data['transform_result'],
        transform_time=data['transform_time'],
        placing_time=data['placing_time'],
        pillage_time=data['pillage_time'],
        extra_count=data['extra_count'],
        extra_removal_times=data['extra_removal_times'],
        color_red=data['color_red'],
        color_green=data['color_green'],
        color_blue=data['color_blue'],
        helptext=data['helptext'],
    )

    # Store in game state
    game_state.terrains[terrain.id] = terrain

    # Display summary
    if len(terrain.output) >= 3:
        output_str = f"F:{terrain.output[0]} S:{terrain.output[1]} T:{terrain.output[2]}"
    else:
        output_str = "N/A"
    print(f"[TERRAIN {terrain.id}] {terrain.name} ({terrain.rule_name})")
    print(f"  Movement: {terrain.movement_cost}, Defense: {terrain.defense_bonus:+d}%")
    print(f"  Output: {output_str}")


__all__ = [
    "handle_ruleset_control",
    "handle_ruleset_terrain_control",
    "handle_ruleset_terrain_flag",
    "handle_ruleset_terrain",
    "handle_ruleset_summary",
    "handle_ruleset_description_part",
    "handle_ruleset_nation_sets",
    "handle_ruleset_nation_groups",
    "handle_ruleset_nation",
    "handle_nation_availability",
    "handle_ruleset_game",
    "handle_ruleset_specialist",
    "handle_ruleset_disaster",
    "handle_ruleset_trade",
    "handle_ruleset_resource",
    "handle_ruleset_achievement",
    "handle_ruleset_tech_flag",
    "handle_ruleset_extra_flag",
    "handle_ruleset_unit_class",
    "handle_ruleset_base",
    "handle_ruleset_road",
    "handle_ruleset_unit_class_flag",
    "handle_ruleset_unit_flag",
    "handle_ruleset_unit_bonus",
    "handle_ruleset_tech",
    "handle_ruleset_government_ruler_title",
    "handle_ruleset_government",
    "handle_ruleset_unit",
    "handle_ruleset_action",
    "handle_ruleset_action_enabler",
    "handle_ruleset_action_auto",
    "handle_ruleset_extra",
    "handle_ruleset_goods",
]