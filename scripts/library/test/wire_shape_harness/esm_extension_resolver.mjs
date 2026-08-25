// Node ESM resolve hook for the compiled generated client.
//
// The generated Angular client is authored the way a bundler-targeted Angular
// workspace authors TypeScript: relative imports carry no file extension
// (`./core/query-params`). That is correct for the consuming frontend
// repository, and it is what `tsc` faithfully preserves in the JavaScript it
// emits -- but Node's ESM loader requires a full specifier. Rather than
// rewriting the emitted client (which would mean the gate no longer runs the
// code as shipped), this hook resolves the same specifier Node would, and
// only on failure retries the two forms `tsc` can have produced.

import { existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

const RETRY_SUFFIXES = ['.js', '/index.js'];

/**
 * @param {string} specifier
 * @param {{parentURL?: string}} context
 * @param {Function} nextResolve
 */
export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (error) {
    const relative = specifier.startsWith('./') || specifier.startsWith('../');
    if (!relative || context.parentURL === undefined) {
      throw error;
    }
    for (const suffix of RETRY_SUFFIXES) {
      const candidate = new URL(`${specifier}${suffix}`, context.parentURL);
      if (existsSync(fileURLToPath(candidate))) {
        return { url: pathToFileURL(fileURLToPath(candidate)).href, shortCircuit: true };
      }
    }
    throw error;
  }
}
