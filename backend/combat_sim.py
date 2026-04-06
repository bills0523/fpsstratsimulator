from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Dict, List, Literal

# Simulation resolution and baseline combat power scalar.
TICKS_PER_SECOND = 10
BASE_POWER = 10.0

AngleState = Literal["holding_45", "peeking_90", "neutral"]
UtilityState = Literal[
    "flashed",
    "smoke_pushing_seen",
    "smoke_pushing_unseen",
    "stunned",
    "slowed",
    "vulnerable",
    "clear",
]


@dataclass
class Player:
    """Static player inputs for a duel simulation."""
    name: str
    elo_factor: float
    weapon_category: int
    distance_to_target: float
    angle_state: AngleState
    utility_state: UtilityState


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


def get_angle_modifier(state: AngleState, elo_factor: float) -> float:
    """Return angle multiplier using elo_factor."""
    if state == "holding_45":
        return 1.0 + (0.25 * elo_factor)
    if state == "peeking_90":
        return 1.0 + (0.20 * elo_factor)
    return 1.0


def get_utility_modifier(state: UtilityState, elo_factor: float) -> float:
    """Return utility multiplier for the shooter's state."""
    if state == "flashed":
        return 0.0
    if state == "smoke_pushing_seen":
        return 0.25
    if state == "smoke_pushing_unseen":
        return 1.5
    if state == "stunned":
        return 0.15 + (elo_factor * 0.10)
    if state == "slowed":
        return 0.6
    return 1.0


def calculate_combat_power(player: Player, opponent: Player) -> float:
    """
    Compute combat power C = Base * W * A * U.
    If opponent is vulnerable, multiply player's final power by 1.25.
    """
    weapon_mod = get_weapon_modifier(player.weapon_category, player.distance_to_target)
    angle_mod = get_angle_modifier(player.angle_state, player.elo_factor)
    utility_mod = get_utility_modifier(player.utility_state, player.elo_factor)

    power = BASE_POWER * weapon_mod * angle_mod * utility_mod

    if opponent.utility_state == "vulnerable":
        power *= 1.25

    return power


def simulate_duel(player1: Player, player2: Player, max_seconds: int = 30) -> Dict[str, object]:
    """
    Tick-based duel simulation (10 ticks/sec). Each tick:
    - Compute combat power for each player
    - Convert to kill probabilities
    - Roll for lethal shots, allow trades
    """
    # Timeline captures per-tick narration for debugging or playback.
    timeline: List[str] = []
    total_ticks = max_seconds * TICKS_PER_SECOND

    for tick in range(1, total_ticks + 1):
        # Compute power every tick to reflect current state.
        c1 = calculate_combat_power(player1, player2)
        c2 = calculate_combat_power(player2, player1)

        if c1 + c2 == 0:
            timeline.append(
                f"Tick {tick}: Both players have zero combat power. No shots fired."
            )
            continue

        p1 = c1 / (c1 + c2)
        p2 = c2 / (c1 + c2)

        # Stochastic kill resolution based on power-weighted probabilities.
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
        elo_factor=1.0,
        weapon_category=3,
        distance_to_target=25.0,
        angle_state="holding_45",
        utility_state="clear",
    )
    p2 = Player(
        name="Player 2",
        elo_factor=0.2,
        weapon_category=2,
        distance_to_target=25.0,
        angle_state="peeking_90",
        utility_state="smoke_pushing_seen",
    )

    result = simulate_duel(p1, p2, max_seconds=10)
    print(json.dumps(result, indent=2))
