// Non-vacuity self-test for the generated-client reader.
//
// Runs the REAL reader (`readClientClasses`, the function the live harness reads every emitted
// client with) over a planted client file the Python side wrote, and records what it read: each
// method it understood (verb, route path, the names of its request arguments) and each method it
// refused. The gate's Python side asserts that a method taking request arguments and a method
// taking NONE (only the trailing request options) are both read, and that a method whose first
// parameter is neither is still refused -- so the reader can neither miss a route nor swallow a
// shape it does not understand.

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { ensureHarnessNodeEnv } from './node_env.mjs';
import { loadTypescript, readClientClasses } from './client_introspection.mjs';

function parseArgs(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 2) {
    parsed[argv[index].replace(/^--/u, '')] = argv[index + 1];
  }
  for (const required of ['node-dir', 'client-file', 'out']) {
    if (parsed[required] === undefined) {
      throw new Error(
        `Missing required argument --${required}. Usage: node client_introspection_self_test.mjs ` +
          `--node-dir <dir> --client-file <planted .client.ts> --out <results.json>`,
      );
    }
  }
  return parsed;
}

const parsed = parseArgs(process.argv.slice(2));
const env = await ensureHarnessNodeEnv(path.resolve(parsed['node-dir']));
const ts = await loadTypescript(env);
const classes = await readClientClasses(ts, [path.resolve(parsed['client-file'])]);

const report = classes.map((ngClass) => ({
  className: ngClass.className,
  methods: ngClass.methods.map((method) => ({
    name: method.name,
    httpVerb: method.httpVerb,
    routePath: method.routePath,
    argNames: method.argsMembers.map((member) => member.name),
    argsHasDefault: method.argsHasDefault,
  })),
  introspectionFailures: ngClass.introspectionFailures,
}));

const outPath = path.resolve(parsed.out);
await mkdir(path.dirname(outPath), { recursive: true });
await writeFile(outPath, `${JSON.stringify({ classes: report }, null, 2)}\n`, 'utf8');
