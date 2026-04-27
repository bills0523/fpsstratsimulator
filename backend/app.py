from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.combat_sim import (
    Player,
    Utility,
    get_default_utility_radius,
    normalize_utility_type,
    simulate_teamfight,
)

ANGLE_STATES = {"holding_45", "peeking_90", "neutral"}
ELO_FACTORS = {
    "low": 0.35,
    "mid": 0.75,
    "high": 1.0,
}

app = FastAPI(title="FPS Strat Simulator Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlayerIcon(BaseModel):
    """Serialized player token placed on the map."""

    id: str
    x: float
    y: float
    side: Literal["attack", "defense"] = "attack"
    weapon_category: int = Field(default=3, ge=1, le=4)
    angle_state: Optional[str] = None


class UtilityIcon(BaseModel):
    """Serialized utility placement from the board."""

    id: str
    type: str
    x: float
    y: float
    radius: Optional[float] = Field(default=None, ge=0)
    side: Literal["attack", "defense"] = "attack"


class SimRequest(BaseModel):
    """Request payload describing the live board state to simulate."""

    map: str
    created_at: Optional[str] = None
    players: List[PlayerIcon]
    utilities: List[UtilityIcon] = Field(default_factory=list)
    elo: str = Field(default="mid", description="low | mid | high")
    max_seconds: int = Field(default=18, ge=1, le=60)
    seed: Optional[int] = None


def resolve_angle_state(player: PlayerIcon) -> Literal["holding_45", "peeking_90", "neutral"]:
    """Normalize requested angle state with a side-aware fallback."""
    if player.angle_state in ANGLE_STATES:
        return player.angle_state  # type: ignore[return-value]
    return "peeking_90" if player.side == "attack" else "holding_45"


def build_players(payload: SimRequest) -> List[Player]:
    """Convert request models into combat-sim players."""
    elo_factor = ELO_FACTORS.get(payload.elo, ELO_FACTORS["mid"])
    return [
        Player(
            name=player.id,
            x=player.x,
            y=player.y,
            elo_factor=elo_factor,
            weapon_category=player.weapon_category,
            distance_to_target=0.0,
            angle_state=resolve_angle_state(player),
            side=player.side,
        )
        for player in payload.players
    ]


def build_utilities(payload: SimRequest) -> List[Utility]:
    """Convert request models into combat-sim utilities, skipping non-combat items."""
    utilities: List[Utility] = []
    for utility in payload.utilities:
        utility_type = normalize_utility_type(utility.type)
        if utility_type is None:
            continue
        radius = utility.radius
        if radius is None or radius <= 0:
            radius = get_default_utility_radius(utility_type)
        utilities.append(
            Utility(
                type=utility_type,
                x=utility.x,
                y=utility.y,
                radius=radius,
                side=utility.side,
            )
        )
    return utilities


@app.get("/health")
def health() -> dict[str, str]:
    """Simple health endpoint for frontend connectivity checks."""
    return {"status": "ok"}


@app.post("/simulate")
def simulate(payload: SimRequest) -> dict[str, object]:
    """Resolve the current board state into a live teamfight simulation."""
    attack_count = sum(1 for player in payload.players if player.side == "attack")
    defense_count = sum(1 for player in payload.players if player.side == "defense")

    if attack_count == 0 or defense_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Place at least one attacker and one defender on the map before simulating.",
        )

    utilities = build_utilities(payload)
    result = simulate_teamfight(
        players=build_players(payload),
        active_utilities=utilities,
        max_seconds=payload.max_seconds,
        seed=payload.seed,
    )
    result.update(
        {
            "map": payload.map,
            "elo": payload.elo,
            "player_count": len(payload.players),
            "utility_count": len(utilities),
        }
    )
    return result
