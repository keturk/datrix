// Node toolchain bootstrap for the wire-shape round-trip harness.
//
// One package directory, created outside every package repo, holding the
// exact toolchain the harness needs: the TypeScript compiler (used BOTH to
// type-check the response-shape probes and to parse the generated client
// sources through the real compiler API rather than a regex), and the Angular
// runtime the generated client classes import, so those classes execute
// exactly as shipped instead of being re-implemented here.
//
// Versions are pinned so a gate run is reproducible. The TypeScript pin
// matches the version the generated TypeScript projects themselves declare.

import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';

/** TypeScript compiler version. Matches the pin generated projects declare. */
export const TYPESCRIPT_VERSION = '^5.5.0';

/** Angular runtime version the generated client classes are executed against. */
export const ANGULAR_VERSION = '^22.1.3';

/** RxJS version Angular's HttpClient returns Observables from. */
export const RXJS_VERSION = '^7.8.2';

const HARNESS_PACKAGE_NAME = 'datrix-wire-shape-harness';
const NPM_INSTALL_TIMEOUT_MS = 600_000;

/**
 * @typedef {object} HarnessNodeEnv
 * @property {string} nodeDir Directory holding the harness `node_modules`.
 * @property {string} tscJs Absolute path to the TypeScript compiler entry script.
 * @property {string} typescriptApiUrl `file://` URL of the TypeScript JS API module.
 */

function harnessManifest() {
  return {
    name: HARNESS_PACKAGE_NAME,
    version: '0.0.0',
    private: true,
    type: 'module',
    dependencies: {
      '@angular/common': ANGULAR_VERSION,
      '@angular/compiler': ANGULAR_VERSION,
      '@angular/core': ANGULAR_VERSION,
      rxjs: RXJS_VERSION,
      typescript: TYPESCRIPT_VERSION,
    },
  };
}

/**
 * Run a command, resolving with its exit code and captured output.
 *
 * @param {string} command
 * @param {string[]} args
 * @param {string} cwd
 * @param {number} timeoutMs
 * @param {{shell?: boolean}} options `shell` is required only for launchers
 *   Windows exposes as `.cmd` shims (npm); it must stay off for an absolute
 *   executable path, which the shell would split on its spaces.
 * @returns {Promise<{code: number, stdout: string, stderr: string}>}
 */
export function runCommand(command, args, cwd, timeoutMs, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      shell: options.shell === true,
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(
        new Error(
          `Command timed out after ${timeoutMs} ms: ${command} ${args.join(' ')} (cwd=${cwd})`,
        ),
      );
    }, timeoutMs);
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code: code === null ? -1 : code, stdout, stderr });
    });
  });
}

/**
 * Ensure the pinned harness toolchain is installed under `nodeDir`.
 *
 * The install is skipped when the manifest on disk already matches the pinned
 * one and every dependency directory is present, so repeated gate runs pay it
 * once.
 *
 * @param {string} nodeDir Directory to create the harness package in.
 * @returns {Promise<HarnessNodeEnv>}
 */
export async function ensureHarnessNodeEnv(nodeDir) {
  await mkdir(nodeDir, { recursive: true });
  const manifest = harnessManifest();
  const manifestPath = path.join(nodeDir, 'package.json');
  let manifestOnDisk = '';
  if (existsSync(manifestPath)) {
    manifestOnDisk = await readFile(manifestPath, 'utf8');
  }
  const wanted = `${JSON.stringify(manifest, null, 2)}\n`;
  if (manifestOnDisk !== wanted) {
    await writeFile(manifestPath, wanted, 'utf8');
  }

  const installed = Object.keys(manifest.dependencies).every((dependency) =>
    existsSync(path.join(nodeDir, 'node_modules', ...dependency.split('/'), 'package.json')),
  );
  if (!installed || manifestOnDisk !== wanted) {
    const result = await runCommand(
      'npm',
      ['install', '--no-audit', '--no-fund', '--loglevel', 'error'],
      nodeDir,
      NPM_INSTALL_TIMEOUT_MS,
      { shell: true },
    );
    if (result.code !== 0) {
      throw new Error(
        `Installing the wire-shape harness toolchain into ${nodeDir} failed ` +
          `(npm exit ${result.code}). Expected the pinned dependencies ` +
          `${JSON.stringify(manifest.dependencies)} to install. Fix: make the npm ` +
          `registry reachable from this machine, then re-run the gate.\n` +
          `${result.stdout}\n${result.stderr}`,
      );
    }
  }

  const tscJs = path.join(nodeDir, 'node_modules', 'typescript', 'lib', 'tsc.js');
  const typescriptApi = path.join(nodeDir, 'node_modules', 'typescript', 'lib', 'typescript.js');
  for (const required of [tscJs, typescriptApi]) {
    if (!existsSync(required)) {
      throw new Error(
        `The wire-shape harness toolchain is incomplete: ${required} is missing after ` +
          `installing into ${nodeDir}. Expected the pinned typescript ` +
          `${TYPESCRIPT_VERSION} to provide it. Fix: delete ${nodeDir} and re-run the gate.`,
      );
    }
  }
  return {
    nodeDir,
    tscJs,
    typescriptApiUrl: new URL(`file://${typescriptApi.replace(/\\/g, '/')}`).href,
  };
}
