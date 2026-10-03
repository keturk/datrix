import { Utils, wrap } from '@mikro-orm/core';
import type { EntityMetadata } from '@mikro-orm/core';

/**
 * Recursively convert object keys from snake_case to camelCase.
 * Used to normalise incoming JSON request bodies so that NestJS DTOs
 * (which use camelCase property names) accept snake_case payloads.
 */
export function camelizeKeys(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(camelizeKeys);
  if (obj !== null && typeof obj === 'object' && !(obj instanceof Date)) {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k.replace(/_([a-z])/g, (_: string, c: string) => c.toUpperCase()),
        camelizeKeys(v),
      ]),
    );
  }
  return obj;
}

/**
 * An entity's plain fields (`toPOJO()`), with every property its metadata
 * marks `hidden` removed -- the generator marks each withheld field (hidden,
 * sensitive, encrypted, or an always-redacted name) so. A related entity or
 * collection the plain object nests is pruned by its OWN metadata, so a
 * withheld field of a related row is dropped too. A key the metadata does
 * not declare is dropped rather than passed through: only a declared,
 * visible property ever reaches a response.
 */
function withholdEntityFields(pojo: Record<string, unknown>, meta: EntityMetadata): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(pojo)) {
    const prop = meta.properties[key];
    if (prop === undefined || prop.hidden) {
      continue;
    }
    fields[key] = prop.targetMeta === undefined ? value : withholdRelatedFields(value, prop.targetMeta);
  }
  return fields;
}

/** A related value as `toPOJO()` nests it: a plain object, a list of them, or a bare key. */
function withholdRelatedFields(value: unknown, meta: EntityMetadata): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => withholdRelatedFields(item, meta));
  }
  if (value !== null && typeof value === 'object' && !(value instanceof Date)) {
    return withholdEntityFields(value as Record<string, unknown>, meta);
  }
  return value;
}

/**
 * Recursively convert object keys from camelCase to snake_case.
 * Used to normalise outgoing JSON response bodies so that API consumers
 * receive the standard snake_case field names defined in the .dtrx schema.
 * The SAME function every serverless HTTP adapter's JSON response leg calls,
 * so a serverless JSON body uses the same encoder as the REST route on this
 * language.
 * An ORM entity is serialized without its withheld fields
 * (`withholdEntityFields`), whichever route returns it.
 */
export function snakeizeKeys(obj: unknown): unknown {
  if (Array.isArray(obj)) {
    return obj.map(snakeizeKeys);
  }
  if (obj instanceof Date) {
    return obj;
  }
  if (typeof Buffer !== 'undefined' && obj instanceof Buffer) {
    return obj;
  }
  if (Utils.isEntity(obj)) {
    const pojo = wrap(obj).toPOJO() as Record<string, unknown>;
    return snakeizeKeys(withholdEntityFields(pojo, wrap(obj, true).__meta));
  }
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k.replace(/[A-Z]/g, (c: string) => `_${c.toLowerCase()}`),
        snakeizeKeys(v),
      ]),
    );
  }
  return obj;
}
