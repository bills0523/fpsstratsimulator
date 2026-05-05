const TICKS_PER_SECOND = 10;
const BASE_POWER = 10.0;
const PIXELS_PER_METER = 10.0;
const DEFAULT_UTILITY_RADII = {
  "util-flash": 22.0,
  "util-molly": 32.0,
  "util-sphere": 34.0,
  "util-line": 46.0,
  "util-recon": 52.0,
  "util-trap": 28.0,
  "util-stun": 38.0,
};
const UTILITY_TYPE_ALIASES = {
  blind: "util-flash",
  flash: "util-flash",
  molly: "util-molly",
  smoke: "util-sphere",
  sphere: "util-sphere",
  wall: "util-line",
  line: "util-line",
  reveal: "util-recon",
  recon: "util-recon",
  trap: "util-trap",
  stun: "util-stun",
};
const ANGLE_STATES = new Set(["holding_45", "peeking_90", "neutral"]);
const ELO_FACTORS = {
  low: 0.35,
  mid: 0.75,
  high: 1.0,
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function roundTo(value, digits = 2) {
  const power = 10 ** digits;
  return Math.round(value * power) / power;
}

function createSeededRandom(seed) {
  if (!Number.isFinite(seed)) {
    return Math.random;
  }

  let state = (Math.abs(Math.trunc(seed)) || 1) % 2147483647;
  if (state === 0) state = 1;

  return () => {
    state = (state * 48271) % 2147483647;
    return (state - 1) / 2147483646;
  };
}

function getPlayerLabel(player) {
  return player.displayName || player.name;
}

function normalizeUtilityType(rawType) {
  if (DEFAULT_UTILITY_RADII[rawType]) return rawType;
  return UTILITY_TYPE_ALIASES[rawType] || null;
}

function getDefaultUtilityRadius(utilityType) {
  return DEFAULT_UTILITY_RADII[utilityType];
}

function resolveAngleState(player) {
  if (ANGLE_STATES.has(player.angle_state)) {
    return player.angle_state;
  }
  return player.side === "attack" ? "peeking_90" : "holding_45";
}

function buildPlayers(payload) {
  const eloFactor = ELO_FACTORS[payload.elo] ?? ELO_FACTORS.mid;
  return payload.players.map((player) => ({
    name: player.id,
    displayName: player.display_name || player.id,
    x: player.x,
    y: player.y,
    eloFactor,
    weaponCategory: player.weapon_category,
    distanceToTarget: 0,
    angleState: resolveAngleState(player),
    side: player.side,
  }));
}

function buildUtilities(payload) {
  const utilities = [];
  for (const utility of payload.utilities || []) {
    const utilityType = normalizeUtilityType(utility.type);
    if (!utilityType) continue;
    let radius = utility.radius;
    if (!Number.isFinite(radius) || radius <= 0) {
      radius = getDefaultUtilityRadius(utilityType);
    }
    utilities.push({
      type: utilityType,
      x: utility.x,
      y: utility.y,
      radius,
      side: utility.side,
    });
  }
  return utilities;
}

function checkUtilityIntersection(player, utilities) {
  const intersecting = [];
  for (const utility of utilities) {
    const distance = Math.hypot(player.x - utility.x, player.y - utility.y);
    if (distance > utility.radius) continue;
    if (utility.type === "util-sphere" || utility.type === "util-line") {
      intersecting.push(utility.type);
    } else if (utility.side !== player.side) {
      intersecting.push(utility.type);
    }
  }
  return intersecting;
}

function getDistanceMeters(player, opponent) {
  return Math.hypot(player.x - opponent.x, player.y - opponent.y) / PIXELS_PER_METER;
}

function getWeaponModifier(category, distance) {
  if (category === 1) return distance <= 20 ? 0.8 : 0.3;
  if (category === 2) {
    if (distance <= 15) return 1.2;
    return distance > 20 ? 0.1 : 0.6;
  }
  if (category === 3) return 1.0;
  if (category === 4) {
    if (distance < 20) return 0.7;
    if (distance >= 80) return 5.0;
    return 1.0;
  }
  return 1.0;
}

function getAngleModifier(state, eloFactor, side) {
  if (state === "holding_45") {
    const base = 1.0 + 0.25 * eloFactor;
    return side === "defense" ? base + 0.15 : base;
  }
  if (state === "peeking_90") {
    const base = 1.0 + 0.2 * eloFactor;
    return side === "attack" ? base + 0.15 : base;
  }
  return 1.0;
}

function getUtilityModifier(intersectingTypes, eloFactor, enemyHasLos = true) {
  if (intersectingTypes.includes("util-flash")) return 0.0;
  if (intersectingTypes.includes("util-stun")) return 0.15 + eloFactor * 0.1;
  if (intersectingTypes.includes("util-trap")) return 0.6;
  if (
    intersectingTypes.includes("util-sphere") ||
    intersectingTypes.includes("util-line")
  ) {
    return enemyHasLos ? 0.25 : 1.5;
  }
  return 1.0;
}

function calculateCombatPower(player, opponent, activeUtilities) {
  const playerIntersections = checkUtilityIntersection(player, activeUtilities);
  const opponentIntersections = checkUtilityIntersection(opponent, activeUtilities);

  const distanceMeters = getDistanceMeters(player, opponent);
  const weaponModifier = getWeaponModifier(player.weaponCategory, distanceMeters);
  let angleModifier = getAngleModifier(player.angleState, player.eloFactor, player.side);

  if (opponentIntersections.includes("util-recon")) {
    angleModifier = 1.0;
  }

  const utilityModifier = getUtilityModifier(playerIntersections, player.eloFactor);
  let power = BASE_POWER * weaponModifier * angleModifier * utilityModifier;

  if (opponentIntersections.includes("util-molly")) {
    power *= 1.25;
  }
  if (opponentIntersections.includes("util-recon")) {
    power *= 1.15;
  }

  return power;
}

function pairNearestEnemies(players) {
  const attackers = players.filter((player) => player.side === "attack");
  const defenders = players.filter((player) => player.side === "defense");
  const distances = [];

  for (const attacker of attackers) {
    for (const defender of defenders) {
      distances.push([getDistanceMeters(attacker, defender), attacker, defender]);
    }
  }

  distances.sort((left, right) => left[0] - right[0]);
  const usedAttackers = new Set();
  const usedDefenders = new Set();
  const pairs = [];

  for (const [, attacker, defender] of distances) {
    if (usedAttackers.has(attacker.name) || usedDefenders.has(defender.name)) continue;
    usedAttackers.add(attacker.name);
    usedDefenders.add(defender.name);
    pairs.push([attacker, defender]);
  }

  return pairs;
}

export function simulatePayload(payload) {
  const attackCount = payload.players.filter((player) => player.side === "attack").length;
  const defenseCount = payload.players.filter((player) => player.side === "defense").length;

  if (!attackCount || !defenseCount) {
    throw new Error("Place at least one attacker and one defender on the map before simulating.");
  }

  const players = buildPlayers(payload);
  const activeUtilities = buildUtilities(payload);
  const rng = createSeededRandom(payload.seed);
  const totalTicks = clamp((payload.max_seconds || 18) * TICKS_PER_SECOND, 10, 600);
  const roster = players.map((player) => ({ ...player }));
  const alive = new Map(roster.map((player) => [player.name, true]));
  const events = [];

  for (let tick = 1; tick <= totalTicks; tick += 1) {
    const livingPlayers = roster.filter((player) => alive.get(player.name));
    const attacksAlive = livingPlayers.filter((player) => player.side === "attack");
    const defensesAlive = livingPlayers.filter((player) => player.side === "defense");

    if (!attacksAlive.length || !defensesAlive.length) {
      const winnerSide = attacksAlive.length ? "attack" : "defense";
      return {
        result: `${winnerSide} wins`,
        winner_side: winnerSide,
        tick: tick - 1,
        events,
        survivors: livingPlayers.map(getPlayerLabel),
        side_counts: {
          attack: attacksAlive.length,
          defense: defensesAlive.length,
        },
        map: payload.map,
        elo: payload.elo,
        player_count: payload.players.length,
        utility_count: activeUtilities.length,
      };
    }

    const engagements = pairNearestEnemies(livingPlayers);
    const casualties = new Set();

    for (const [attacker, defender] of engagements) {
      const attackPower = calculateCombatPower(attacker, defender, activeUtilities);
      const defensePower = calculateCombatPower(defender, attacker, activeUtilities);
      const combinedPower = attackPower + defensePower;

      if (combinedPower <= 0) continue;

      const engagementScale = Math.min(0.32, 0.06 + combinedPower / (BASE_POWER * 60.0));
      const attackerKillChance = Math.min(
        0.9,
        engagementScale *
          (attackPower / combinedPower) *
          (1.0 + attacker.eloFactor * 0.05)
      );
      const defenderKillChance = Math.min(
        0.9,
        engagementScale *
          (defensePower / combinedPower) *
          (1.0 + defender.eloFactor * 0.05)
      );

      const attackerKill = rng() < attackerKillChance;
      const defenderKill = rng() < defenderKillChance;

      if (attackerKill && defenderKill) {
        casualties.add(attacker.name);
        casualties.add(defender.name);
        events.push({
          tick,
          type: "trade",
          actor: getPlayerLabel(attacker),
          target: getPlayerLabel(defender),
          power: {
            attack: roundTo(attackPower),
            defense: roundTo(defensePower),
          },
          event: `Tick ${tick}: ${getPlayerLabel(attacker)} and ${getPlayerLabel(
            defender
          )} trade (${attackPower.toFixed(2)} vs ${defensePower.toFixed(2)} power).`,
        });
      } else if (attackerKill) {
        casualties.add(defender.name);
        events.push({
          tick,
          type: "kill",
          actor: getPlayerLabel(attacker),
          target: getPlayerLabel(defender),
          power: {
            attack: roundTo(attackPower),
            defense: roundTo(defensePower),
          },
          event: `Tick ${tick}: ${getPlayerLabel(attacker)} eliminates ${getPlayerLabel(
            defender
          )} (${attackPower.toFixed(2)} vs ${defensePower.toFixed(2)} power).`,
        });
      } else if (defenderKill) {
        casualties.add(attacker.name);
        events.push({
          tick,
          type: "kill",
          actor: getPlayerLabel(defender),
          target: getPlayerLabel(attacker),
          power: {
            attack: roundTo(attackPower),
            defense: roundTo(defensePower),
          },
          event: `Tick ${tick}: ${getPlayerLabel(defender)} eliminates ${getPlayerLabel(
            attacker
          )} (${defensePower.toFixed(2)} vs ${attackPower.toFixed(2)} power).`,
        });
      }
    }

    for (const name of casualties) {
      alive.set(name, false);
    }
  }

  const livingPlayers = roster.filter((player) => alive.get(player.name));
  const attacksAlive = livingPlayers.filter((player) => player.side === "attack");
  const defensesAlive = livingPlayers.filter((player) => player.side === "defense");
  let winnerSide = null;
  if (attacksAlive.length > defensesAlive.length) winnerSide = "attack";
  if (defensesAlive.length > attacksAlive.length) winnerSide = "defense";

  return {
    result: "timeout",
    winner_side: winnerSide,
    tick: totalTicks,
    events,
    survivors: livingPlayers.map(getPlayerLabel),
    side_counts: {
      attack: attacksAlive.length,
      defense: defensesAlive.length,
    },
    map: payload.map,
    elo: payload.elo,
    player_count: payload.players.length,
    utility_count: activeUtilities.length,
  };
}

function waitForNextFrame() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}

function buildRuntimeInfo(mode) {
  if (mode === "worker") {
    return {
      chip: "Worker",
      summary: "runtime://browser-worker",
      detail:
        "Simulation runs entirely in the browser on a background thread. No server or network is required.",
    };
  }

  return {
    chip: "Inline",
    summary: "runtime://browser-inline",
    detail:
      "Simulation runs entirely in the browser with no server or network. This fallback is used when worker threads are unavailable.",
  };
}

export function createSimulationRunner() {
  let worker = null;
  let workerAttempted = false;
  let mode = "inline";
  let nextRequestId = 0;
  const pending = new Map();

  function cleanupWorker() {
    if (worker) worker.terminate();
    worker = null;
    mode = "inline";
    for (const { reject, timeoutId } of pending.values()) {
      clearTimeout(timeoutId);
      reject(new Error("Browser worker failed. Falling back to inline simulation."));
    }
    pending.clear();
  }

  function handleWorkerMessage(event) {
    const { requestId, result, error } = event.data || {};
    const request = pending.get(requestId);
    if (!request) return;
    pending.delete(requestId);
    clearTimeout(request.timeoutId);
    if (error) {
      request.reject(new Error(error));
      return;
    }
    request.resolve(result);
  }

  function postWorkerRequest(type, payload, timeoutMs = 2500) {
    if (!worker) {
      return Promise.reject(new Error("Worker is not available."));
    }

    return new Promise((resolve, reject) => {
      const requestId = `sim-${nextRequestId}`;
      nextRequestId += 1;
      const timeoutId = window.setTimeout(() => {
        pending.delete(requestId);
        reject(new Error("Browser worker did not respond in time."));
      }, timeoutMs);

      pending.set(requestId, { resolve, reject, timeoutId });
      worker.postMessage({ type, requestId, payload });
    });
  }

  async function ensureWorker() {
    if (workerAttempted) return worker;
    workerAttempted = true;

    if (typeof Worker === "undefined") {
      mode = "inline";
      return null;
    }

    try {
      worker = new Worker(new URL("./simulationWorker.js", import.meta.url), {
        type: "module",
      });
      worker.addEventListener("message", handleWorkerMessage);
      worker.addEventListener("error", () => cleanupWorker());
      await postWorkerRequest("ping", null, 1200);
      mode = "worker";
      return worker;
    } catch (error) {
      cleanupWorker();
      return null;
    }
  }

  async function runInline(payload) {
    mode = "inline";
    await waitForNextFrame();
    return simulatePayload(payload);
  }

  return {
    async run(payload) {
      const start = performance.now();

      try {
        const activeWorker = await ensureWorker();
        if (activeWorker) {
          const result = await postWorkerRequest("simulate", payload, 8000);
          return {
            ...result,
            runtime: {
              mode: "worker",
              elapsed_ms: roundTo(performance.now() - start, 1),
            },
          };
        }
      } catch (error) {
        cleanupWorker();
      }

      const result = await runInline(payload);
      return {
        ...result,
        runtime: {
          mode: "inline",
          elapsed_ms: roundTo(performance.now() - start, 1),
        },
      };
    },
    async warmup() {
      try {
        await ensureWorker();
      } catch (error) {
        cleanupWorker();
      }
      return buildRuntimeInfo(mode);
    },
    getRuntimeInfo() {
      return buildRuntimeInfo(mode);
    },
  };
}
