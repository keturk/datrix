/**
 * Tiles helpers for Datrix ``Tiles.generate`` builtin.
 * Generates vector tiles from GeoJSON input via Tippecanoe.
 */

import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

export async function _tilesGenerate(
  options: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const maxZoom = Number(options.maxZoom ?? 14);
  const minZoom = Number(options.minZoom ?? 0);

  const features: unknown[] = [];
  for (const [key, layer] of Object.entries(options)) {
    if (key === 'maxZoom' || key === 'minZoom') continue;
    if (Array.isArray(layer)) features.push(...layer);
  }

  const geojson = { type: 'FeatureCollection', features };
  const tippecanoe = process.env.TIPPECANOE_PATH ?? 'tippecanoe';

  try {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tiles-'));
    const inputPath = path.join(tmpDir, 'input.geojson');
    const outputPath = path.join(tmpDir, 'output.mbtiles');
    fs.writeFileSync(inputPath, JSON.stringify(geojson));
    execFileSync(tippecanoe, [
      '-o', outputPath,
      `-z${maxZoom}`,
      `-Z${minZoom}`,
      '--no-tile-compression',
      inputPath,
    ]);
    const tileData = fs.readFileSync(outputPath);
    fs.rmSync(tmpDir, { recursive: true, force: true });
    return { count: features.length, tiles: [], mbtiles: tileData };
  } catch {
    console.warn(`tippecanoe not found at ${tippecanoe}, returning stub result`);
    return { count: features.length, tiles: [] };
  }
}
