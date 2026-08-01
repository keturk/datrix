/**
 * Archive helpers for Datrix ``Archive.unzip`` builtin.
 * Extracts ZIP archives into in-memory key-value maps.
 */

import AdmZip from 'adm-zip';

export function _archiveUnzip(rawData: Buffer): Record<string, Buffer> {
  const zip = new AdmZip(rawData);
  const result: Record<string, Buffer> = {};
  for (const entry of zip.getEntries()) {
    if (!entry.isDirectory) {
      result[entry.entryName] = entry.getData();
    }
  }
  return result;
}
