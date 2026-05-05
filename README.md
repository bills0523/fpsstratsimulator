<!-- Project overview and quick-start usage for the simulator. -->
# FPS Strat Simulator

A web-based 2D Valorant strategy simulator prototype. Current progress includes:

- JSON Schemas for weapons, agents, and the Ascent map.
- Canvas-based frontend for placing players/utilities and playing back simulations.
- In-browser teamfight simulation with an automatic worker fallback.
- Elo-driven combat resolution that considers side, weapon class, angle state, and utility overlap.

## Project Structure

- `index.html`: One-page project showcase and introduction.
- `demo.html`: Frontend simulator UI and canvas playback logic.
- `browserSimulation.js`: Browser-native simulation engine and runtime selector.
- `simulationWorker.js`: Background worker used when the browser supports it.
- `backend/`: Optional Python reference implementation from the earlier API-backed version.
- `schemas/`: JSON schemas for core data structures.
- `showcase/`: Showcase styling and demo image slots.

## Use Frontend

Recommended local flow:

1. Open `demo.html`
2. Place at least one attacker and one defender
3. Click `Run Simulation`

No FastAPI server, API base URL, or environment configuration is required. The page runs the simulation locally in the browser and will use a background worker automatically when available.

## Static Hosting

The demo is static-host friendly:

- Opening `demo.html` directly from disk works without setup.
- GitHub Pages works without custom build steps or runtime configuration.
- Browsers that allow worker threads use `simulationWorker.js` to keep the UI responsive.
- Browsers that block workers fall back to inline execution automatically.

## Next Steps

- Load real map and weapon data from JSON files.
- Add richer replay and round-state logic on top of the live simulation response.
- Replace placeholder map with scaled Ascent layout.
