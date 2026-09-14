/**
 * Metrics for pubsub contract violations (auto-generated).
 */
import * as client from 'prom-client';

export const contractViolationCounter = new client.Counter({
  name: 'contract_violations_total',
  help: 'Number of event contract violations',
  labelNames: ['event', 'clause'],
});
