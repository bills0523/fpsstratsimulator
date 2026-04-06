from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Simulation resolution and safety cap.
TICKS_PER_SECOND = 10
MAX_TICKS = 300

# FastAPI application for the 2D simulation service.
app = FastAPI(title="Valorant 2D Sim Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Icon(BaseModel):
    """Serialized token/utility on the 2D map."""
    id: str
    type: str
    x: float
    y: float


class SimRequest(BaseModel):
    """Request payload describing the map, players, and utilities to simulate."""
    map: str
    created_at: Optional[str] = None
    players: List[Icon]
    utilities: List[Icon] = Field(default_factory=list)
    elo: str = Field(default="mid", description="low | mid | high")
    weapon: Optional[str] = None


@dataclass
class PlayerState:
    """Runtime state for each player during the tick loop."""
    id: str
    x: float
    y: float
    weapon: str
    hp: float = 100.0
    alive: bool = True
    blinded_ticks: int = 0
    engaged_target: Optional[str] = None
    engaged_progress: int = 0


@dataclass
class UtilityState:
    """Runtime state for placed utilities."""
    id: str
    type: str
    x: float
    y: float


# Simplified weapon balance data used by the tick simulation.
WEAPONS = {
    "rifle": {
        "base_damage": 35.0,
        "fire_rate_rps": 9.0,
        "range_m": 35.0,
    },
    "smg": {
        "base_damage": 26.0,
        "fire_rate_rps": 12.0,
        "range_m": 22.0,
    },
    "sniper": {
        "base_damage": 95.0,
        "fire_rate_rps": 1.5,
        "range_m": 60.0,
    },
}

# Elo presets adjust accuracy, utility impact, and time-to-kill.
ELO_PRESETS = {
    "low": {
        "randomness": 0.35,
        "utility_impact": 0.3,
        "ttk_multiplier": 1.5,
    },
    "mid": {
        "randomness": 0.2,
        "utility_impact": 0.6,
        "ttk_multiplier": 1.0,
    },
    "high": {
        "randomness": 0.05,
        "utility_impact": 1.0,
        "ttk_multiplier": 0.4,
    },
}


def distance(a: PlayerState, b: PlayerState) -> float:
    """Euclidean distance between two players."""
    return hypot(a.x - b.x, a.y - b.y)


def in_radius(px: float, py: float, ux: float, uy: float, radius: float) -> bool:
    """True if point (px, py) is inside a utility radius."""
    return hypot(px - ux, py - uy) <= radius


def get_weapon(name: Optional[str]) -> Dict[str, float]:
    """Resolve a weapon by name, falling back to rifle."""
    if name and name in WEAPONS:
        return WEAPONS[name]
    return WEAPONS["rifle"]


def compute_ttk_ticks(weapon: Dict[str, float], elo_cfg: Dict[str, float]) -> int:
    """Convert weapon stats + elo tuning into a tick-based TTK."""
    base_damage = weapon["base_damage"]
    fire_rate = weapon["fire_rate_rps"]
    shots_to_kill = max(1, int((100 + base_damage - 1) // base_damage))
    ttk_s = max(0.05, (shots_to_kill - 1) / fire_rate)
    ttk_s *= elo_cfg["ttk_multiplier"]
    return max(1, int(ttk_s * TICKS_PER_SECOND))


@app.post("/simulate")
def simulate(req: SimRequest):
    """Main simulation endpoint: resolves utility effects and combat per tick."""
    elo_cfg = ELO_PRESETS.get(req.elo, ELO_PRESETS["mid"])

    # Initialize runtime entities from the request payload.
    players = [
        PlayerState(id=p.id, x=p.x, y=p.y, weapon=req.weapon or "rifle")
        for p in req.players
    ]
    utilities = [UtilityState(id=u.id, type=u.type, x=u.x, y=u.y) for u in req.utilities]

    events: List[Dict[str, object]] = []
    tick = 0

    while tick < MAX_TICKS:
        tick += 1

        # Track who is standing inside smoke for accuracy penalties.
        smoke_players = set()

        for u in utilities:
            if u.type == "flash":
                for p in players:
                    if p.alive and in_radius(p.x, p.y, u.x, u.y, 28.0):
                        if p.blinded_ticks == 0:
                            events.append({
                                "tick": tick,
                                "type": "blind",
                                "actor": u.id,
                                "target": p.id,
                                "event": f"Tick {tick}: {p.id} blinded by Flash",
                            })
                        p.blinded_ticks = max(p.blinded_ticks, int(1.5 * TICKS_PER_SECOND))
            elif u.type == "smoke":
                for p in players:
                    if p.alive and in_radius(p.x, p.y, u.x, u.y, 35.0):
                        smoke_players.add(p.id)
            elif u.type == "molly":
                for p in players:
                    if p.alive and in_radius(p.x, p.y, u.x, u.y, 25.0):
                        p.hp -= 2.5 * elo_cfg["utility_impact"]
                        if p.hp <= 0 and p.alive:
                            p.alive = False
                            events.append({
                                "tick": tick,
                                "type": "molly_kill",
                                "actor": u.id,
                                "target": p.id,
                                "event": f"Tick {tick}: {p.id} eliminated by Molly",
                            })

        # Decay blinded ticks each frame.
        for p in players:
            if p.blinded_ticks > 0:
                p.blinded_ticks -= 1

        # Stop early if one or fewer players remain.
        alive_players = [p for p in players if p.alive]
        if len(alive_players) <= 1:
            break

        for attacker in alive_players:
            # Select the closest available target.
            targets = [p for p in alive_players if p.id != attacker.id]
            if not targets:
                continue
            target = min(targets, key=lambda t: distance(attacker, t))

            weapon = get_weapon(attacker.weapon)
            # Only engage if the target is within effective range.
            if distance(attacker, target) > weapon["range_m"]:
                attacker.engaged_target = None
                attacker.engaged_progress = 0
                continue

            base_accuracy = 0.55
            randomness = elo_cfg["randomness"]
            utility_bonus = 0.0
            if target.blinded_ticks > 0:
                utility_bonus += 0.25 * elo_cfg["utility_impact"]
            if attacker.id in smoke_players or target.id in smoke_players:
                utility_bonus -= 0.25 * elo_cfg["utility_impact"]

            hit_chance = max(0.05, min(0.95, base_accuracy + utility_bonus - randomness))

            if attacker.engaged_target != target.id:
                attacker.engaged_target = target.id
                attacker.engaged_progress = 0

            # Increment progress toward a kill based on TTK ticks.
            ttk_ticks = compute_ttk_ticks(weapon, elo_cfg)
            attacker.engaged_progress += 1

            if hit_chance < 0.5:
                attacker.engaged_progress = max(attacker.engaged_progress - 1, 0)

            if attacker.engaged_progress >= ttk_ticks:
                target.alive = False
                attacker.engaged_target = None
                attacker.engaged_progress = 0
                events.append({
                    "tick": tick,
                    "type": "kill",
                    "actor": attacker.id,
                    "target": target.id,
                    "event": f"Tick {tick}: {attacker.id} kills {target.id}",
                })

        if tick >= MAX_TICKS:
            break

    survivors = [p.id for p in players if p.alive]
    return {
        "map": req.map,
        "elo": req.elo,
        "ticks": tick,
        "events": events,
        "survivors": survivors,
    }
