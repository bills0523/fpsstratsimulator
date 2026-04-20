const DEFAULT_CONE_PRESETS = {
  small: { spread: 31.5, range: 72, rays: 40 },
  medium: { spread: 52.5, range: 112, rays: 44 },
  large: { spread: 77, range: 144, rays: 48 },
};

const BLACK_TARGET = [0, 0, 0];
const CYAN_GREEN_TARGETS = [
  [26, 205, 196],
  [60, 220, 170],
  [0, 180, 170],
];
const DARK_BLUE_TARGETS = [
  [18, 43, 92],
  [26, 58, 110],
  [14, 34, 74],
];

function colorDistanceSq(r, g, b, target) {
  const dr = r - target[0];
  const dg = g - target[1];
  const db = b - target[2];
  return dr * dr + dg * dg + db * db;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export class VisionEngine {
  constructor(options = {}) {
    this.conePresets = options.conePresets || DEFAULT_CONE_PRESETS;
    this.collisionGrid = new Uint8Array(0);
    this.width = 0;
    this.height = 0;
    this.offscreenCanvas = null;
    this.offscreenCtx = null;
  }

  /**
   * Read the rendered map image into an offscreen canvas and classify every
   * pixel as either solid or walkable. The result is stored in a packed
   * Uint8Array for very fast grid sampling in the ray stepper.
   */
  initializeMap(imageElement, width, height) {
    const nextWidth = Math.max(1, Math.floor(width));
    const nextHeight = Math.max(1, Math.floor(height));

    if (
      !this.offscreenCanvas ||
      this.width !== nextWidth ||
      this.height !== nextHeight
    ) {
      this.offscreenCanvas = document.createElement("canvas");
      this.offscreenCanvas.width = nextWidth;
      this.offscreenCanvas.height = nextHeight;
      this.offscreenCtx = this.offscreenCanvas.getContext("2d", {
        willReadFrequently: true,
      });
      this.collisionGrid = new Uint8Array(nextWidth * nextHeight);
      this.width = nextWidth;
      this.height = nextHeight;
    } else {
      this.offscreenCtx.clearRect(0, 0, this.width, this.height);
    }

    this.offscreenCtx.drawImage(imageElement, 0, 0, this.width, this.height);
    const imageData = this.offscreenCtx.getImageData(0, 0, this.width, this.height);
    const data = imageData.data;

    for (let index = 0, pixelIndex = 0; index < data.length; index += 4, pixelIndex += 1) {
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];
      const a = data[index + 3];
      this.collisionGrid[pixelIndex] = this.#isSolidPixel(r, g, b, a) ? 1 : 0;
    }
  }

  /**
   * Cast a fan of DDA rays through the image-derived collision grid and return
   * the hit points that define the visible polygon.
   */
  calculateCone(originX, originY, facingAngle, coneType) {
    if (!this.collisionGrid.length) return [];

    const preset = this.conePresets[coneType] || this.conePresets.medium;
    const clampedOriginX = clamp(originX, 0, this.width - 1);
    const clampedOriginY = clamp(originY, 0, this.height - 1);
    const start = facingAngle - (preset.spread * Math.PI) / 360;
    const sweep = (preset.spread * Math.PI) / 180;
    const step = sweep / preset.rays;
    const points = [];

    for (let rayIndex = 0; rayIndex <= preset.rays; rayIndex += 1) {
      const angle = start + step * rayIndex;
      points.push(this.#castRay(clampedOriginX, clampedOriginY, angle, preset.range));
    }

    return points;
  }

  #isSolidPixel(r, g, b, a) {
    if (a < 12) return 1;

    const nearBlack = colorDistanceSq(r, g, b, BLACK_TARGET) <= 52 * 52;
    const nearCyanGreen = CYAN_GREEN_TARGETS.some(
      (target) => colorDistanceSq(r, g, b, target) <= 68 * 68
    );
    const nearDarkBlue = DARK_BLUE_TARGETS.some(
      (target) => colorDistanceSq(r, g, b, target) <= 60 * 60
    );

    if (nearBlack || nearCyanGreen) return 1;
    if (nearDarkBlue) return 0;

    const luminance = r * 0.2126 + g * 0.7152 + b * 0.0722;
    const cyanLean = g > 95 && b > 80 && g > r * 1.15;
    const darkBlueLean = b > 50 && b >= g + 10 && g >= r && luminance < 105;

    if (cyanLean) return 1;
    if (darkBlueLean) return 0;

    return luminance < 28 ? 1 : 0;
  }

  #castRay(originX, originY, angle, maxRange) {
    const dirX = Math.cos(angle);
    const dirY = Math.sin(angle);

    if (Math.abs(dirX) < 0.000001 && Math.abs(dirY) < 0.000001) {
      return { x: originX, y: originY };
    }

    let mapX = Math.floor(originX);
    let mapY = Math.floor(originY);

    const deltaDistX = dirX === 0 ? Number.POSITIVE_INFINITY : Math.abs(1 / dirX);
    const deltaDistY = dirY === 0 ? Number.POSITIVE_INFINITY : Math.abs(1 / dirY);

    let stepX = 0;
    let stepY = 0;
    let sideDistX = Number.POSITIVE_INFINITY;
    let sideDistY = Number.POSITIVE_INFINITY;

    if (dirX < 0) {
      stepX = -1;
      sideDistX = (originX - mapX) * deltaDistX;
    } else {
      stepX = 1;
      sideDistX = (mapX + 1 - originX) * deltaDistX;
    }

    if (dirY < 0) {
      stepY = -1;
      sideDistY = (originY - mapY) * deltaDistY;
    } else {
      stepY = 1;
      sideDistY = (mapY + 1 - originY) * deltaDistY;
    }

    let travelled = 0;

    while (travelled <= maxRange) {
      if (sideDistX < sideDistY) {
        travelled = sideDistX;
        sideDistX += deltaDistX;
        mapX += stepX;
      } else {
        travelled = sideDistY;
        sideDistY += deltaDistY;
        mapY += stepY;
      }

      if (!this.#inBounds(mapX, mapY)) {
        const boundaryDistance = Math.min(travelled, maxRange);
        return {
          x: clamp(originX + dirX * boundaryDistance, 0, this.width),
          y: clamp(originY + dirY * boundaryDistance, 0, this.height),
        };
      }

      if (this.#isSolidCell(mapX, mapY)) {
        const hitDistance = Math.max(0, Math.min(travelled, maxRange));
        return {
          x: clamp(originX + dirX * hitDistance, 0, this.width),
          y: clamp(originY + dirY * hitDistance, 0, this.height),
        };
      }
    }

    return {
      x: clamp(originX + dirX * maxRange, 0, this.width),
      y: clamp(originY + dirY * maxRange, 0, this.height),
    };
  }

  #isSolidCell(x, y) {
    return this.collisionGrid[y * this.width + x] === 1;
  }

  #inBounds(x, y) {
    return x >= 0 && x < this.width && y >= 0 && y < this.height;
  }
}
