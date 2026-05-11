from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DEV_ORIGINS = [
    "null",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

app = FastAPI(title="FPS Strat Simulator Backend")


def get_allowed_origins() -> List[str]:
    """Resolve CORS origins from env or fall back to local development hosts."""
    configured = os.getenv("SIM_ALLOWED_ORIGINS", "").strip()
    if not configured:
        return LOCAL_DEV_ORIGINS
    if configured == "*":
        return ["*"]
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def serve_frontend_file(path: str, media_type: Optional[str] = None) -> FileResponse:
    """Serve a top-level frontend file from the project root."""
    return FileResponse(PROJECT_ROOT / path, media_type=media_type)


allowed_origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VisionContext(BaseModel):
    """Derived vision state produced by the frontend before simulation."""

    angle_state: Optional[str] = None
    supported_by_friendly: bool = False
    revealed_to_enemy: bool = False
    source_id: Optional[str] = None
    cone_type: Optional[str] = None


class PlayerIcon(BaseModel):
    """Serialized player token placed on the map."""

    id: str
    display_name: Optional[str] = None
    x: float
    y: float
    side: Literal["attack", "defense"] = "attack"
    weapon_category: int = Field(default=3, ge=1, le=4)
    angle_state: Optional[str] = None
    vision_context: Optional[VisionContext] = None


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
    if player.vision_context and player.vision_context.angle_state in ANGLE_STATES:
        return player.vision_context.angle_state  # type: ignore[return-value]
    if player.angle_state in ANGLE_STATES:
        return player.angle_state  # type: ignore[return-value]
    return "peeking_90" if player.side == "attack" else "holding_45"


def build_players(payload: SimRequest) -> List[Player]:
    """Convert request models into combat-sim players."""
    elo_factor = ELO_FACTORS.get(payload.elo, ELO_FACTORS["mid"])
    return [
        Player(
            name=player.id,
            display_name=player.display_name or player.id,
            x=player.x,
            y=player.y,
            elo_factor=elo_factor,
            weapon_category=player.weapon_category,
            distance_to_target=0.0,
            angle_state=resolve_angle_state(player),
            side=player.side,
            vision_supported=bool(player.vision_context and player.vision_context.supported_by_friendly),
            revealed_to_enemy=bool(player.vision_context and player.vision_context.revealed_to_enemy),
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


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    """Serve the project landing page from the same origin as the API."""
    return serve_frontend_file("index.html")


@app.get("/index.html", include_in_schema=False)
def serve_index_html() -> FileResponse:
    return serve_frontend_file("index.html")


@app.get("/demo.html", include_in_schema=False)
def serve_demo() -> FileResponse:
    """Serve the simulator UI from the backend origin."""
    return serve_frontend_file("demo.html")


@app.get("/styles.css", include_in_schema=False)
def serve_styles() -> FileResponse:
    return serve_frontend_file("styles.css", media_type="text/css")


@app.get("/visionEngine.js", include_in_schema=False)
def serve_vision_engine() -> FileResponse:
    return serve_frontend_file("visionEngine.js", media_type="text/javascript")


@app.get("/browserSimulation.js", include_in_schema=False)
def serve_browser_simulation() -> FileResponse:
    """Serve the browser-native simulation module used by demo.html."""
    return serve_frontend_file("browserSimulation.js", media_type="text/javascript")


@app.get("/simulationWorker.js", include_in_schema=False)
def serve_simulation_worker() -> FileResponse:
    """Serve the worker module used for background browser simulations."""
    return serve_frontend_file("simulationWorker.js", media_type="text/javascript")


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


app.mount("/assets", StaticFiles(directory=PROJECT_ROOT / "assets"), name="assets")
app.mount("/showcase", StaticFiles(directory=PROJECT_ROOT / "showcase"), name="showcase")
