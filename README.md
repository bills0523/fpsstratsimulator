<!-- Project overview and quick-start usage for the simulator. -->
# FPS Strat Simulator

A web-based 2D Valorant strategy simulator prototype. Current progress includes:

- JSON Schemas for weapons, agents, and the Ascent map.
- Canvas-based frontend for placing players/utilities and playing back simulations.
- FastAPI backend with a live teamfight simulation endpoint.
- Elo-driven combat resolution that considers side, weapon class, angle state, and utility overlap.

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

To run live combat simulation from the demo:

1. Start the backend with `uvicorn backend.app:app --reload`
2. Open `demo.html`
3. Place at least one attacker and one defender
4. Set the backend URL in the right sidebar and click `Run Simulation`

The frontend is static, so a deployed website still needs a separately hosted FastAPI backend URL for the live simulation button to work.

## Next Steps

- Load real map and weapon data from JSON files.
- Add richer replay and round-state logic on top of the live simulation response.
- Replace placeholder map with scaled Ascent layout.
