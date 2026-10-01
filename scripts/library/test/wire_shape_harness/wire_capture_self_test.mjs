// Non-vacuity self-test for the wire capture the harness installs.
//
// Drives the REAL capture path: a real Angular `HttpClient` over `fetch`,
// provisioned by the same `createHttpClientProviders` the live harness uses,
// with the same recorder interceptor, against a throwaway HTTP server bound to
// the loopback interface on an ephemeral port. The server answers with planted
// responses -- every body carries a synthetic secret-shaped string -- and this
// script writes down what the recorder captured for each, so the gate's Python
// side can assert that status, content type and body SHAPE arrive and that the
// planted value does not.
//
// Nothing here talks to a generated backend, a gateway, or any host other than
// the server this script starts and stops itself.

import { createServer } from 'node:http';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { ensureHarnessNodeEnv } from './node_env.mjs';
import {
  createHttpClientProviders,
  createWireRecorder,
  loadAngularRuntime,
} from './wire_capture.mjs';

const LOOPBACK_HOST = '127.0.0.1';
const SLOW_RESPONSE_DELAY_MS = 300;

function parseArgs(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 2) {
    parsed[argv[index].replace(/^--/u, '')] = argv[index + 1];
  }
  for (const required of ['node-dir', 'out', 'planted-secret']) {
    if (parsed[required] === undefined) {
      throw new Error(
        `Missing required argument --${required}. Usage: node wire_capture_self_test.mjs ` +
          `--node-dir <dir> --out <results.json> --planted-secret <value>`,
      );
    }
  }
  return parsed;
}

/** The planted responses the throwaway server answers with, by path. */
function plantedResponses(secret) {
  return {
    '/answered': {
      status: 200,
      contentType: 'application/json; charset=utf-8',
      body: JSON.stringify({
        orderId: secret,
        lineItems: [{ sku: secret, quantity: 2 }],
        total: 3.5,
        note: null,
      }),
    },
    '/refused': {
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: secret }),
    },
    '/empty': { status: 204, contentType: null, body: '' },
    '/binary': {
      status: 200,
      contentType: 'application/octet-stream',
      body: Buffer.from(secret, 'utf8'),
    },
    '/slow': {
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ slowField: secret }),
      delayMs: SLOW_RESPONSE_DELAY_MS,
    },
    '/fast': {
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ fastField: secret }),
    },
  };
}

function startServer(responses) {
  const server = createServer((request, response) => {
    const planted = responses[request.url];
    if (planted === undefined) {
      response.writeHead(500, { 'Content-Type': 'text/plain' });
      response.end('unplanted path');
      return;
    }
    const answer = () => {
      const headers = planted.contentType === null ? {} : { 'Content-Type': planted.contentType };
      response.writeHead(planted.status, headers);
      response.end(planted.body);
    };
    if (planted.delayMs === undefined) {
      answer();
    } else {
      setTimeout(answer, planted.delayMs);
    }
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, LOOPBACK_HOST, () => resolve(server));
  });
}

async function settle(promise) {
  try {
    await promise;
    return 'resolved';
  } catch {
    return 'rejected';
  }
}

async function main(argv) {
  const parsed = parseArgs(argv);
  const nodeDir = path.resolve(parsed['node-dir']);
  await ensureHarnessNodeEnv(nodeDir);
  const { core, commonHttp, rxjs } = await loadAngularRuntime(nodeDir);

  const recorder = createWireRecorder(commonHttp, rxjs);
  const injector = core.createEnvironmentInjector(
    createHttpClientProviders(core, commonHttp, [recorder.interceptor]),
    core.Injector.create({ providers: [] }),
  );
  const http = injector.get(commonHttp.HttpClient);

  const server = await startServer(plantedResponses(parsed['planted-secret']));
  const baseUrl = `http://${LOOPBACK_HOST}:${server.address().port}`;
  const cases = [];
  try {
    const sequential = [
      ['answered-json', '/answered', {}],
      ['refused-json', '/refused', {}],
      ['empty-204', '/empty', {}],
      ['binary-arraybuffer', '/binary', { responseType: 'arraybuffer' }],
    ];
    for (const [name, urlPath, options] of sequential) {
      const attempt = recorder.begin();
      const outcome = await settle(rxjs.firstValueFrom(http.get(`${baseUrl}${urlPath}`, options)));
      cases.push({ name, outcome, captured: attempt.captured });
    }

    // Two requests in flight at once, the slow one started first. Each must
    // capture into the attempt that issued it: a response that arrives after
    // the harness has moved on to the next attempt must not overwrite it.
    const slowAttempt = recorder.begin();
    const slow = settle(rxjs.firstValueFrom(http.get(`${baseUrl}/slow`)));
    const fastAttempt = recorder.begin();
    const fast = settle(rxjs.firstValueFrom(http.get(`${baseUrl}/fast`)));
    const [slowOutcome, fastOutcome] = await Promise.all([slow, fast]);
    cases.push({ name: 'in-flight-slow', outcome: slowOutcome, captured: slowAttempt.captured });
    cases.push({ name: 'in-flight-fast', outcome: fastOutcome, captured: fastAttempt.captured });
  } finally {
    await new Promise((resolve) => {
      server.close(resolve);
    });
  }

  const outPath = path.resolve(parsed.out);
  await mkdir(path.dirname(outPath), { recursive: true });
  await writeFile(outPath, `${JSON.stringify({ cases }, null, 2)}\n`, 'utf8');
  return 0;
}

main(process.argv.slice(2)).then(
  (code) => {
    process.exitCode = code;
  },
  (error) => {
    process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
    process.exitCode = 1;
  },
);
