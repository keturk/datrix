/**
 * JSON helpers for Datrix ``JSON.parseTabular`` builtin.
 * Parses raw tabular data (CSV, etc.) into arrays of objects.
 */

import { parse as csvParse } from 'csv-parse/sync';

/**
 * Pluggable parser registry: maps format names to parser functions.
 * Add domain-specific parsers here (e.g., shapefile via shpjs, DAT via fixed-width parser).
 */
const _TABULAR_PARSERS: Record<string, (data: Buffer | string) => Record<string, unknown>[]> = {};

export function _jsonParseTabular(
  rawData: Buffer | string,
  formatHint: string,
): Record<string, unknown>[] {
  const fmt = String(formatHint).trim().toLowerCase();

  if (fmt === 'csv' || fmt.startsWith('csv|')) {
    return _parseCsv(rawData, String(formatHint));
  }

  const parser = _TABULAR_PARSERS[fmt];
  if (parser) {
    return parser(rawData);
  }

  throw new Error(
    `Unsupported tabular format '${formatHint}'. ` +
    `Available: ${['csv', ...Object.keys(_TABULAR_PARSERS)].sort().join(', ')}. ` +
    'Register a custom parser in _TABULAR_PARSERS for domain-specific formats.',
  );
}

/**
 * Parse CSV text, optionally skipping ragged leading header lines.
 *
 * Supports ``csv`` (header on row 0) and ``csv|skip=N`` / ``csv|header=N``
 * (the column-name row is at 0-indexed line ``N``; every line before it is
 * discarded and data records start after it). ``csv|delimiter=X`` selects a
 * single-character delimiter other than comma (e.g. ``\t`` for TSV).
 */
function _parseCsv(rawData: Buffer | string, formatHint: string): Record<string, unknown>[] {
  let text = Buffer.isBuffer(rawData) ? rawData.toString('utf-8') : String(rawData);
  const { headerRow, delimiter } = _parseCsvSpec(formatHint);
  if (headerRow > 0) {
    const lines = text.split(/\r\n|\r|\n/);
    if (headerRow >= lines.length) {
      throw new Error(`CSV header row ${headerRow} is beyond the file's ${lines.length} lines.`);
    }
    text = lines.slice(headerRow).join('\n');
  }
  const rows = csvParse(text, {
    columns: true,
    skip_empty_lines: true,
    delimiter,
  }) as Record<string, unknown>[];
  return rows.map((row) => {
    const cleaned: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(row)) {
      cleaned[k.trim()] = v;
    }
    return cleaned;
  });
}

/**
 * Parse a ``csv`` format hint into ``{ headerRow, delimiter }``.
 *
 * ``headerRow`` is the 0-indexed line that holds the column names (0 for a
 * plain ``csv``). ``delimiter`` is the field separator (``,`` by default).
 * ``skip`` and ``header`` are aliases for the header-row index; supplying both
 * with conflicting values is rejected.
 */
function _parseCsvSpec(formatHint: string): { headerRow: number; delimiter: string } {
  const parts = formatHint.split('|').map((part) => part.trim()).filter((part) => part.length > 0);
  if (parts.length === 0 || parts[0].toLowerCase() !== 'csv') {
    throw new Error("csv format hints must start with 'csv'.");
  }
  let headerRow = 0;
  let headerSet = false;
  let delimiter = ',';
  for (const token of parts.slice(1)) {
    const eq = token.indexOf('=');
    if (eq < 0) {
      throw new Error(`Invalid csv token '${token}'. Expected key=value.`);
    }
    const key = token.slice(0, eq).trim().toLowerCase();
    const value = token.slice(eq + 1);
    if (key === 'skip' || key === 'header') {
      const row = Number.parseInt(value, 10);
      if (!Number.isInteger(row) || row < 0) {
        throw new Error(`csv '${key}' must be >= 0, got '${value}'.`);
      }
      if (headerSet && row !== headerRow) {
        throw new Error(`Conflicting csv header rows: ${headerRow} and ${row}.`);
      }
      headerRow = row;
      headerSet = true;
    } else if (key === 'delimiter') {
      delimiter = value === '\\t' ? '\t' : value;
      if (delimiter.length !== 1) {
        throw new Error(`csv delimiter must be a single character, got '${value}'.`);
      }
    } else {
      throw new Error(`Unknown csv directive '${key}'. Supported: skip, header, delimiter.`);
    }
  }
  return { headerRow, delimiter };
}
