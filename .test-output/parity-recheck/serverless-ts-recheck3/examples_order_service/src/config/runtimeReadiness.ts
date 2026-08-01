/**
 * Strict runtime readiness check. Auto-generated. Do not edit.
 *
 * Resolves every required config key and secret handle through the SAME runtime
 * clients the application uses (RemoteConfigClient from './remoteConfig' and
 * SecretsService from '../examples_order_service/secrets/secrets.service'), proving the live
 * backend actually serves each item under the deployed identity. Reports status
 * by logical handle/key and rendered platform name. NEVER captures, logs, or
 * returns a resolved value.
 *
 * Because it exercises the real resolution path against the real backend (Key
 * Vault / Secrets Manager / mounted files / remote config store), it catches
 * IAM/role denials, wrong mount paths, unreachable backend URLs, wrong
 * label/profile, and missing permissions that a static, generation-time
 * preflight can never prove.
 */
import { Logger } from '@nestjs/common';
import { RemoteConfigClient, RemoteConfigError } from './remoteConfig';
import { SecretsService } from '../examples_order_service/secrets/secrets.service';

const logger = new Logger('RuntimeReadiness');

const KIND_CONFIG = 'config';
const KIND_SECRET = 'secret';
const CONNECTIONS_NAMESPACE = 'connections';

export enum ReadinessStatus {
  OK = 'ok',
  MISSING = 'missing',
  ERROR = 'error',
}

const BLOCKING_STATUSES: ReadinessStatus[] = [ReadinessStatus.MISSING, ReadinessStatus.ERROR];

/** Per-item readiness result. Holds NO secret value -- only identity + status. */
export interface ReadinessItem {
  kind: 'config' | 'secret';
  logicalName: string;
  renderedName: string;
  status: ReadinessStatus;
  detail: string;
}

export interface ReadinessReport {
  ok: boolean;
  items: ReadinessItem[];
}

export function readinessFailures(report: ReadinessReport): ReadinessItem[] {
  return report.items.filter((i) => BLOCKING_STATUSES.includes(i.status));
}

// Required set baked from the runtime-requirements manifest. Values are NEVER baked here.
const REQUIRED_SECRET_HANDLES: Array<[string, string]> = [
  ["db_password", "db_password"],
  ["queues_password", "queues_password"],
];

const REQUIRED_CONFIG_KEYS: Array<[string, string]> = [
  ["db_database", "db_database"],
  ["db_host", "db_host"],
  ["db_port", "db_port"],
  ["db_user", "db_user"],
  ["examples_order_service_base_url", "examples_order_service_base_url"],
  ["mq_brokers", "mq_brokers"],
  ["mq_port", "mq_port"],
  ["queues_host", "queues_host"],
  ["queues_port", "queues_port"],
];

function valueFreeDetail(err: unknown): string {
  if (err instanceof Error) {
    return `${err.constructor.name}: ${err.message}`;
  }
  return String(err);
}

/**
 * Resolve one required secret handle through the live SecretsService.
 *
 * The resolved value is never bound, inspected, logged, or returned: a
 * `string` result classifies OK; `undefined` classifies MISSING (SecretsService
 * returns undefined rather than throwing for an absent secret); a thrown
 * exception classifies ERROR.
 */
async function probeSecret(
  secrets: SecretsService,
  logical: string,
  rendered: string,
): Promise<ReadinessItem> {
  try {
    const value = await secrets.getSecret(logical);
    if (value === undefined) {
      return {
        kind: KIND_SECRET,
        logicalName: logical,
        renderedName: rendered,
        status: ReadinessStatus.MISSING,
        detail: `secret '${logical}' resolved to no value`,
      };
    }
  } catch (err) {
    return {
      kind: KIND_SECRET,
      logicalName: logical,
      renderedName: rendered,
      status: ReadinessStatus.ERROR,
      detail: valueFreeDetail(err),
    };
  }
  return {
    kind: KIND_SECRET,
    logicalName: logical,
    renderedName: rendered,
    status: ReadinessStatus.OK,
    detail: 'resolved',
  };
}

/**
 * Resolve one required config key through the live RemoteConfigClient.
 *
 * Reads the key from the `connections` namespace via the SAME
 * RemoteConfigClient the app uses. A declared-but-unset key or an unknown key
 * is MISSING; any other config error is ERROR.
 */
function probeConfig(
  configClient: RemoteConfigClient,
  logical: string,
  rendered: string,
): ReadinessItem {
  try {
    configClient.get(CONNECTIONS_NAMESPACE, logical);
  } catch (err) {
    if (err instanceof RemoteConfigError) {
      const text = err.message;
      if (text.includes('has no current value') || text.includes('not declared')) {
        return {
          kind: KIND_CONFIG,
          logicalName: logical,
          renderedName: rendered,
          status: ReadinessStatus.MISSING,
          detail: valueFreeDetail(err),
        };
      }
    }
    return {
      kind: KIND_CONFIG,
      logicalName: logical,
      renderedName: rendered,
      status: ReadinessStatus.ERROR,
      detail: valueFreeDetail(err),
    };
  }
  return {
    kind: KIND_CONFIG,
    logicalName: logical,
    renderedName: rendered,
    status: ReadinessStatus.OK,
    detail: 'resolved',
  };
}

/** Resolve every required item through the live clients. Returns a value-free report. */
export async function checkRuntimeReadiness(
  configClient: RemoteConfigClient,
  secrets: SecretsService,
): Promise<ReadinessReport> {
  const items: ReadinessItem[] = [];
  for (const [logical, rendered] of REQUIRED_SECRET_HANDLES) {
    items.push(await probeSecret(secrets, logical, rendered));
  }
  for (const [logical, rendered] of REQUIRED_CONFIG_KEYS) {
    items.push(probeConfig(configClient, logical, rendered));
  }
  const ok = !items.some((i) => BLOCKING_STATUSES.includes(i.status));
  for (const item of items) {
    logger.log(
      `readiness kind=${item.kind} name=${item.logicalName} rendered=${item.renderedName} status=${item.status}`,
    );
  }
  return { ok, items };
}
