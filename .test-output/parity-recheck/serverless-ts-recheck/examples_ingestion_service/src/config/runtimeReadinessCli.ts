/**
 * Standalone runtime readiness CLI. Auto-generated. Do not edit.
 *
 * Run via `node dist/config/runtimeReadinessCli.js` (built) or
 * `npx ts-node src/config/runtimeReadinessCli.ts` (dev). Builds the SAME
 * kind of RemoteConfigClient/SecretsService the application uses, prints one
 * tab-separated line per required item, and exits 0 when ready, 1 otherwise.
 */
import { buildClient } from './remoteConfig';
import { SecretsService } from '../examples_ingestion_service/secrets/secrets.service';
import { checkRuntimeReadiness } from './runtimeReadiness';

const EXIT_OK = 0;
const EXIT_NOT_READY = 1;

async function run(): Promise<number> {
  const configClient = buildClient();
  await configClient.start();
  const secrets = new SecretsService();
  const report = await checkRuntimeReadiness(configClient, secrets);
  for (const item of report.items) {
    process.stdout.write(
      `${item.kind}\t${item.logicalName}\t${item.renderedName}\t${item.status}\n`,
    );
  }
  configClient.stop();
  return report.ok ? EXIT_OK : EXIT_NOT_READY;
}

if (require.main === module) {
  run()
    .then((code) => process.exit(code))
    .catch((err) => {
      // eslint-disable-next-line no-console
      console.error(err);
      process.exit(EXIT_NOT_READY);
    });
}

export { run };
