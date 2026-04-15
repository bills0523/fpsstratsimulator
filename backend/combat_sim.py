from __future__ import annotations

import json
import random
from dataclasses import dataclass
from math import hypot
from typing import Dict, List, Literal

# Simulation resolution and baseline combat power scalar.
TICKS_PER_SECOND = 10
BASE_POWER = 10.0
PIXELS_PER_METER = 10.0

AngleState = Literal["holding_45", "peeking_90", "neutral"]
UtilityType = Literal[
    "util-flash",
    "util-molly",
    "util-sphere",
    "util-line",
    "util-recon",
    "util-trap",
    "util-stun",
]


@dataclass
class Player:
    """Player state used for combat power evaluation."""

    name: str
    x: float
    y: float
    elo_factor: float
    weapon_category: int
    distance_to_target: float
    angle_state: AngleState
    side: Literal["attack", "defense"]


@dataclass
class Utility:
    """Active utility on the map with a circular radius."""

    type: UtilityType
    x: float
    y: float
    radius: float
    side: Literal["attack", "defense"]


def check_utility_intersection(player: Player, utilities: List[Utility]) -> List[UtilityType]:
    """
    Return a list of utility types that intersect the player's position.
    """
    intersecting: List[UtilityType] = []
    for util in utilities:
        distance = hypot(player.x - util.x, player.y - util.y)
        if distance <= util.radius:
            if util.type in ("util-sphere", "util-line"):
                intersecting.append(util.type)
            elif util.side != player.side:
                intersecting.append(util.type)
    return intersecting


def get_distance_m(player: Player, opponent: Player) -> float:
    """Convert pixel distance to meters using a fixed scale."""
    return hypot(player.x - opponent.x, player.y - opponent.y) / PIXELS_PER_METER


def get_weapon_modifier(category: int, distance: float) -> float:
    """Return weapon multiplier based on category and distance."""
    if category == 1:
        return 0.8 if distance <= 20 else 0.3
    if category == 2:
        if distance <= 15:
            return 1.2
        return 0.1 if distance > 20 else 0.6
    if category == 3:
        return 1.0
    if category == 4:
        if distance < 20:
            return 0.7
        if distance >= 80:
            return 5.0
        return 1.0
    return 1.0


def get_angle_modifier(state: AngleState, elo_factor: float, side: str) -> float:
    """Return angle multiplier using elo_factor and side advantage."""
    if state == "holding_45":
        base = 1.0 + (0.25 * elo_factor)
        return base + 0.15 if side == "defense" else base
    if state == "peeking_90":
        base = 1.0 + (0.20 * elo_factor)
        return base + 0.15 if side == "attack" else base
    return 1.0


def get_utility_modifier(
    intersecting_types: List[UtilityType],
    elo_factor: float,
    enemy_has_los: bool = True,
) -> float:
    """
    Return utility multiplier for the shooter's state based on intersecting utilities.
    """
    if "util-flash" in intersecting_types:
        return 0.0
    if "util-stun" in intersecting_types:
        return 0.15 + (elo_factor * 0.10)
    if "util-trap" in intersecting_types:
        return 0.6
    if "util-sphere" in intersecting_types or "util-line" in intersecting_types:
        return 0.25 if enemy_has_los else 1.5
    return 1.0


def calculate_combat_power(
    player: Player, opponent: Player, active_utilities: List[Utility]
) -> float:
    """
    Compute combat power:
    C = Base * W * A * U, with external modifiers from opponent intersections.
    """
    player_intersections = check_utility_intersection(player, active_utilities)
    opponent_intersections = check_utility_intersection(opponent, active_utilities)

    distance_m = get_distance_m(player, opponent)
    weapon_mod = get_weapon_modifier(player.weapon_category, distance_m)
    angle_mod = get_angle_modifier(player.angle_state, player.elo_factor, player.side)

    # If opponent is in recon, nullify their angle advantage.
    if "util-recon" in opponent_intersections:
        angle_mod = 1.0

    utility_mod = get_utility_modifier(player_intersections, player.elo_factor)

    power = BASE_POWER * weapon_mod * angle_mod * utility_mod

    if "util-molly" in opponent_intersections:
        power *= 1.25
    if "util-recon" in opponent_intersections:
        power *= 1.15

    return power


def simulate_duel(
    player1: Player,
    player2: Player,
    active_utilities: List[Utility],
    max_seconds: int = 30,
) -> Dict[str, object]:
    """
    Tick-based duel simulation (10 ticks/sec). Each tick:
    - Compute combat power for each player
    - Convert to kill probabilities
    - Roll for lethal shots, allow trades
    """
    timeline: List[str] = []
    total_ticks = max_seconds * TICKS_PER_SECOND

    for tick in range(1, total_ticks + 1):
        c1 = calculate_combat_power(player1, player2, active_utilities)
        c2 = calculate_combat_power(player2, player1, active_utilities)

        if c1 + c2 == 0:
            timeline.append(
                f"Tick {tick}: Both players have zero combat power. No shots fired."
            )
            continue

        p1 = c1 / (c1 + c2)
        p2 = c2 / (c1 + c2)

        roll1 = random.random() < p1
        roll2 = random.random() < p2

        if roll1 and roll2:
            timeline.append(
                f"Tick {tick}: {player1.name} generated {c1:.2f} Power. "
                f"{player2.name} generated {c2:.2f} Power. Trade kill."
            )
            return {
                "result": "trade",
                "tick": tick,
                "timeline": timeline,
            }

        if roll1:
            timeline.append(
                f"Tick {tick}: {player1.name} generated {c1:.2f} Power. "
                f"{player2.name} generated {c2:.2f} Power. "
                f"{player1.name} killed {player2.name}."
            )
            return {
                "result": f"{player1.name} wins",
                "tick": tick,
                "timeline": timeline,
            }

        if roll2:
            timeline.append(
                f"Tick {tick}: {player1.name} generated {c1:.2f} Power. "
                f"{player2.name} generated {c2:.2f} Power. "
                f"{player2.name} killed {player1.name}."
            )
            return {
                "result": f"{player2.name} wins",
                "tick": tick,
                "timeline": timeline,
            }

        timeline.append(
            f"Tick {tick}: {player1.name} generated {c1:.2f} Power. "
            f"{player2.name} generated {c2:.2f} Power. No kill."
        )

    return {
        "result": "timeout",
        "tick": total_ticks,
        "timeline": timeline,
    }


if __name__ == "__main__":
    # Example usage: run a local duel simulation and print the JSON result.
    p1 = Player(
        name="Player 1",
        x=10.0,
        y=15.0,
        elo_factor=1.0,
        weapon_category=3,
        distance_to_target=25.0,
        angle_state="holding_45",
        side="attack",
    )
    p2 = Player(
        name="Player 2",
        x=30.0,
        y=20.0,
        elo_factor=0.2,
        weapon_category=2,
        distance_to_target=25.0,
        angle_state="peeking_90",
        side="defense",
    )
    utils = [
        Utility(type="util-recon", x=20.0, y=18.0, radius=8.0, side="attack"),
        Utility(type="util-molly", x=28.0, y=19.0, radius=5.0, side="attack"),
    ]

    result = simulate_duel(p1, p2, utils, max_seconds=10)
    print(json.dumps(result, indent=2))
