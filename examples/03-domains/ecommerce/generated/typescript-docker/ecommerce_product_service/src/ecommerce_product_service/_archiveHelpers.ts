/**
 * Archive helpers for the Datrix ``Archive.unzip`` / ``Archive.zip`` builtins.
 * Extracts ZIP archives into in-memory key-value maps and bundles such maps
 * back into ZIP bytes.
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

export interface ArchiveZipOptions {
  /** DEFLATE members (default) or STORE them for already-compressed content. */
  compress?: boolean;
}

const ARCHIVE_ZIP_OPTION_KEYS: ReadonlySet<string> = new Set(['compress']);
/** Fixed member timestamp (the ZIP epoch) so identical inputs give identical bytes. */
const ARCHIVE_FIXED_MEMBER_TIME = new Date(1980, 0, 1, 0, 0, 0);

/**
 * Validate one member name: a relative POSIX path inside the archive. An
 * absolute path, a drive letter, a `.`/`..` segment, a backslash or a NUL would
 * let the archive escape its extraction directory, so they are rejected here
 * rather than shipped to whoever unpacks it.
 */
function _archiveMemberName(name: string): string {
  if (name === '' || name === '/') {
    throw new Error(
      "Archive.zip member name must not be empty. Use a relative path such as 'report.html' or 'reports/2024/' for an empty directory.",
    );
  }
  if (name.includes('\0') || name.includes('\\')) {
    throw new Error(
      `Archive.zip member name ${JSON.stringify(name)} contains a NUL or backslash; use '/' as the separator and printable characters only.`,
    );
  }
  if (name.startsWith('/') || (name.length > 1 && name[1] === ':')) {
    throw new Error(
      `Archive.zip member name ${JSON.stringify(name)} is absolute; member names must be relative to the archive root (for example 'reports/report-1.html').`,
    );
  }
  if (name.split('/').some((segment) => segment === '.' || segment === '..')) {
    throw new Error(
      `Archive.zip member name ${JSON.stringify(name)} contains a '.' or '..' segment; an archive member must not be able to escape the directory it is unpacked into.`,
    );
  }
  return name;
}

function _archiveZipCompress(options: ArchiveZipOptions | undefined): boolean {
  if (options === undefined || options === null) {
    return true;
  }
  if (typeof options !== 'object' || Array.isArray(options)) {
    throw new Error(`Archive.zip options must be an object such as {compress: false}; got ${typeof options}.`);
  }
  const unknown = Object.keys(options).filter((key) => !ARCHIVE_ZIP_OPTION_KEYS.has(key)).sort();
  if (unknown.length > 0) {
    throw new Error(
      `Archive.zip received unknown option(s) ${JSON.stringify(unknown)}; valid options: ${JSON.stringify([...ARCHIVE_ZIP_OPTION_KEYS])}.`,
    );
  }
  const compress = options.compress ?? true;
  if (typeof compress !== 'boolean') {
    throw new Error(
      `Archive.zip option 'compress' must be a Boolean (true = DEFLATE, false = STORE for already-compressed members); got ${typeof compress}.`,
    );
  }
  return compress;
}

/**
 * Bundle `{memberName: bytes}` into a ZIP archive -- the inverse of
 * `_archiveUnzip`. A key ending in `/` creates an empty directory entry (it
 * must map to an empty Buffer). Members are written in key order with a fixed
 * timestamp, so the same input always yields the same bytes.
 */
export function _archiveZip(files: Record<string, Buffer>, options?: ArchiveZipOptions): Buffer {
  if (files === null || typeof files !== 'object' || Array.isArray(files)) {
    throw new Error(`Archive.zip expects a Map<String, Bytes> of member name to content; got ${typeof files}.`);
  }
  const compress = _archiveZipCompress(options);
  const zip = new AdmZip();
  for (const [rawName, content] of Object.entries(files)) {
    const name = _archiveMemberName(rawName);
    if (!Buffer.isBuffer(content)) {
      throw new Error(
        `Archive.zip member ${JSON.stringify(name)} must map to Bytes; got ${typeof content}. Encode text with String.toBytes first.`,
      );
    }
    const isDirectory = name.endsWith('/');
    if (isDirectory && content.length > 0) {
      throw new Error(
        `Archive.zip member ${JSON.stringify(name)} names a directory (trailing '/') but carries content; directory entries must map to empty Bytes.`,
      );
    }
    const entry = zip.addFile(name, isDirectory ? Buffer.alloc(0) : content);
    entry.header.time = ARCHIVE_FIXED_MEMBER_TIME;
    // ZIP method 8 is DEFLATE, 0 is STORE; a directory entry has no data to compress.
    entry.header.method = compress && !isDirectory ? 8 : 0;
  }
  return zip.toBuffer();
}
