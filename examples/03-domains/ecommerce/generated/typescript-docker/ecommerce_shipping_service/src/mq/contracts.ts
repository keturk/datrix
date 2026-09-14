/**
 * Event contract validation (auto-generated).
 */
import { ContractViolationError } from '../errors/contract-violation';
import { contractViolationCounter } from './contract-metrics';

export function validateShipmentDispatchedContract(
  shipmentId: string,
  orderId: string,
  trackingNumber: string,
): void {
  if (!((trackingNumber.length > 0))) {
    console.error('contract_violation', {
      event: 'ShipmentDispatched',
      clause: 'trackingNumber.length > 0',
      trackingNumber,
    });
    contractViolationCounter.inc({
      event: 'ShipmentDispatched',
      clause: 'trackingNumber.length > 0',
    });
    throw new ContractViolationError({
      event: 'ShipmentDispatched',
      clause: 'trackingNumber.length > 0',
      actual: {
        trackingNumber,
      },
    });
  }
}

export function validateShipmentFailedContract(
  shipmentId: string,
  orderId: string,
  reason: string,
): void {
  if (!((reason.length > 0))) {
    console.error('contract_violation', {
      event: 'ShipmentFailed',
      clause: 'reason.length > 0',
      reason,
    });
    contractViolationCounter.inc({
      event: 'ShipmentFailed',
      clause: 'reason.length > 0',
    });
    throw new ContractViolationError({
      event: 'ShipmentFailed',
      clause: 'reason.length > 0',
      actual: {
        reason,
      },
    });
  }
}

