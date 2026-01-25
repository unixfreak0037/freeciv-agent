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
    "handle_ruleset_trade",
    "handle_ruleset_achievement",
    "handle_ruleset_tech_flag",
    "handle_ruleset_unit_class",
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
]