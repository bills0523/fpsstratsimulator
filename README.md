<!-- Project overview and quick-start usage for the simulator. -->
# FPS Strat Simulator

A web-based 2D Valorant strategy simulator prototype. Current progress includes:

- JSON Schemas for weapons, agents, and the Ascent map.
- Canvas-based frontend for placing players/utilities and playing back simulations.
- FastAPI backend with a tick-based simulation engine (10 ticks/sec, max 300 ticks).
- Elo-driven gunfight logic with utility impact and basic line-of-sight distance checks.

## Project Structure

- `index.html`: One-page project showcase and introduction.
- `demo.html`: Frontend simulator UI and canvas playback logic.
- `backend/app.py`: FastAPI simulation service.
- `backend/requirements.txt`: Backend dependencies.
- `schemas/`: JSON schemas for core data structures.
- `showcase/`: Showcase styling and demo image slots.

## Run Backend

```bash
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload
```

## Use Frontend

Open `index.html` to view the project introduction. Open `demo.html` to use the simulator.

## Next Steps

- Load real map and weapon data from JSON files.
- Add team logic, positioning constraints, and richer utility interactions.
- Replace placeholder map with scaled Ascent layout.
