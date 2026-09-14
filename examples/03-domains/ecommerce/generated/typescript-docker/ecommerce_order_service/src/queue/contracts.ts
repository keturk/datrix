/**
 * Event contract validation (auto-generated).
 */
import { ContractViolationError } from '../errors/contract-violation';
import { contractViolationCounter } from './contract-metrics';

export function validateProcessPaymentContract(
  orderId: string,
  amount: number,
  currency: string,
): void {
  if (!((amount > 0))) {
    console.error('contract_violation', {
      event: 'ProcessPayment',
      clause: 'amount > 0',
      amount,
    });
    contractViolationCounter.inc({
      event: 'ProcessPayment',
      clause: 'amount > 0',
    });
    throw new ContractViolationError({
      event: 'ProcessPayment',
      clause: 'amount > 0',
      actual: {
        amount,
      },
    });
  }
  if (!((currency.length === 3))) {
    console.error('contract_violation', {
      event: 'ProcessPayment',
      clause: 'currency.length == 3',
      currency,
    });
    contractViolationCounter.inc({
      event: 'ProcessPayment',
      clause: 'currency.length == 3',
    });
    throw new ContractViolationError({
      event: 'ProcessPayment',
      clause: 'currency.length == 3',
      actual: {
        currency,
      },
    });
  }
}

export function validateSendOrderConfirmationContract(
  orderId: string,
  customerEmail: string,
  orderNumber: string,
): void {
  if (!((customerEmail.length > 0))) {
    console.error('contract_violation', {
      event: 'SendOrderConfirmation',
      clause: 'customerEmail.length > 0',
      customerEmail,
    });
    contractViolationCounter.inc({
      event: 'SendOrderConfirmation',
      clause: 'customerEmail.length > 0',
    });
    throw new ContractViolationError({
      event: 'SendOrderConfirmation',
      clause: 'customerEmail.length > 0',
      actual: {
        customerEmail,
      },
    });
  }
}

export function validateSettlePaymentContract(
  paymentId: string,
  merchantId: string,
  amount: number,
): void {
  if (!((amount > 0))) {
    console.error('contract_violation', {
      event: 'SettlePayment',
      clause: 'amount > 0',
      amount,
    });
    contractViolationCounter.inc({
      event: 'SettlePayment',
      clause: 'amount > 0',
    });
    throw new ContractViolationError({
      event: 'SettlePayment',
      clause: 'amount > 0',
      actual: {
        amount,
      },
    });
  }
  if (!((merchantId.length > 0))) {
    console.error('contract_violation', {
      event: 'SettlePayment',
      clause: 'merchantId.length > 0',
      merchantId,
    });
    contractViolationCounter.inc({
      event: 'SettlePayment',
      clause: 'merchantId.length > 0',
    });
    throw new ContractViolationError({
      event: 'SettlePayment',
      clause: 'merchantId.length > 0',
      actual: {
        merchantId,
      },
    });
  }
}

