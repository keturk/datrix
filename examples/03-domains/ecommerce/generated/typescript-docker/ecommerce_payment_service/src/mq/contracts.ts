/**
 * Event contract validation (auto-generated).
 */
import { ContractViolationError } from '../errors/contract-violation';
import { contractViolationCounter } from './contract-metrics';

export function validatePaymentProcessedContract(
  paymentId: string,
  orderId: string,
  amount: number,
): void {
  if (!((amount > 0))) {
    console.error('contract_violation', {
      event: 'PaymentProcessed',
      clause: 'amount > 0',
      amount,
    });
    contractViolationCounter.inc({
      event: 'PaymentProcessed',
      clause: 'amount > 0',
    });
    throw new ContractViolationError({
      event: 'PaymentProcessed',
      clause: 'amount > 0',
      actual: {
        amount,
      },
    });
  }
}

export function validatePaymentFailedContract(
  paymentId: string,
  orderId: string,
  reason: string,
): void {
  if (!((reason.length > 0))) {
    console.error('contract_violation', {
      event: 'PaymentFailed',
      clause: 'reason.length > 0',
      reason,
    });
    contractViolationCounter.inc({
      event: 'PaymentFailed',
      clause: 'reason.length > 0',
    });
    throw new ContractViolationError({
      event: 'PaymentFailed',
      clause: 'reason.length > 0',
      actual: {
        reason,
      },
    });
  }
}

export function validatePaymentRefundedContract(
  paymentId: string,
  orderId: string,
  amount: number,
): void {
  if (!((amount > 0))) {
    console.error('contract_violation', {
      event: 'PaymentRefunded',
      clause: 'amount > 0',
      amount,
    });
    contractViolationCounter.inc({
      event: 'PaymentRefunded',
      clause: 'amount > 0',
    });
    throw new ContractViolationError({
      event: 'PaymentRefunded',
      clause: 'amount > 0',
      actual: {
        amount,
      },
    });
  }
}

