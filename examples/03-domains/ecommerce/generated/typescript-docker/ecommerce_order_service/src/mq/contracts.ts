/**
 * Event contract validation (auto-generated).
 */
import { ContractViolationError } from '../errors/contract-violation';
import { contractViolationCounter } from './contract-metrics';
import { Address } from '../dto/address.struct'
import { OrderStatus } from '../enums/order-status.enum'

export function validateOrderCreatedContract(
  orderId: string,
  orderNumber: string,
  customerId: string,
  total: number,
  reservationId: string,
): void {
  if (!((orderNumber.length > 0))) {
    console.error('contract_violation', {
      event: 'OrderCreated',
      clause: 'orderNumber.length > 0',
      orderNumber,
    });
    contractViolationCounter.inc({
      event: 'OrderCreated',
      clause: 'orderNumber.length > 0',
    });
    throw new ContractViolationError({
      event: 'OrderCreated',
      clause: 'orderNumber.length > 0',
      actual: {
        orderNumber,
      },
    });
  }
  if (!((total > 0))) {
    console.error('contract_violation', {
      event: 'OrderCreated',
      clause: 'total > 0',
      total,
    });
    contractViolationCounter.inc({
      event: 'OrderCreated',
      clause: 'total > 0',
    });
    throw new ContractViolationError({
      event: 'OrderCreated',
      clause: 'total > 0',
      actual: {
        total,
      },
    });
  }
}

export function validateOrderConfirmedContract(
  orderId: string,
  paymentId: string | null,
  reservationId: string,
  shippingAddress: Address,
  items: Record<string, any>[],
  estimatedWeight: number,
): void {
  if (!((items.length > 0))) {
    console.error('contract_violation', {
      event: 'OrderConfirmed',
      clause: 'items.length() > 0',
      items,
    });
    contractViolationCounter.inc({
      event: 'OrderConfirmed',
      clause: 'items.length() > 0',
    });
    throw new ContractViolationError({
      event: 'OrderConfirmed',
      clause: 'items.length() > 0',
      actual: {
        items,
      },
    });
  }
  if (!((estimatedWeight > 0))) {
    console.error('contract_violation', {
      event: 'OrderConfirmed',
      clause: 'estimatedWeight > 0',
      estimatedWeight,
    });
    contractViolationCounter.inc({
      event: 'OrderConfirmed',
      clause: 'estimatedWeight > 0',
    });
    throw new ContractViolationError({
      event: 'OrderConfirmed',
      clause: 'estimatedWeight > 0',
      actual: {
        estimatedWeight,
      },
    });
  }
}

export function validateOrderCancelledContract(
  orderId: string,
  reason: string,
  reservationId: string,
): void {
  if (!((reason.length > 0))) {
    console.error('contract_violation', {
      event: 'OrderCancelled',
      clause: 'reason.length > 0',
      reason,
    });
    contractViolationCounter.inc({
      event: 'OrderCancelled',
      clause: 'reason.length > 0',
    });
    throw new ContractViolationError({
      event: 'OrderCancelled',
      clause: 'reason.length > 0',
      actual: {
        reason,
      },
    });
  }
}

export function validateOrderStatusChangedContract(
  orderId: string,
  oldStatus: OrderStatus,
  newStatus: OrderStatus,
): void {
  if (!((oldStatus !== newStatus))) {
    console.error('contract_violation', {
      event: 'OrderStatusChanged',
      clause: 'oldStatus != newStatus',
      newStatus,
      oldStatus,
    });
    contractViolationCounter.inc({
      event: 'OrderStatusChanged',
      clause: 'oldStatus != newStatus',
    });
    throw new ContractViolationError({
      event: 'OrderStatusChanged',
      clause: 'oldStatus != newStatus',
      actual: {
        newStatus,
        oldStatus,
      },
    });
  }
}

