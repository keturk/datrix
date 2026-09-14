/**
 * Event contract validation (auto-generated).
 */
import { ContractViolationError } from '../errors/contract-violation';
import { contractViolationCounter } from './contract-metrics';

export function validateProductCreatedContract(
  productId: string,
  name: string,
  price: number,
): void {
  if (!((name.length > 0))) {
    console.error('contract_violation', {
      event: 'ProductCreated',
      clause: 'name.length > 0',
      name,
    });
    contractViolationCounter.inc({
      event: 'ProductCreated',
      clause: 'name.length > 0',
    });
    throw new ContractViolationError({
      event: 'ProductCreated',
      clause: 'name.length > 0',
      actual: {
        name,
      },
    });
  }
  if (!((price > 0))) {
    console.error('contract_violation', {
      event: 'ProductCreated',
      clause: 'price > 0',
      price,
    });
    contractViolationCounter.inc({
      event: 'ProductCreated',
      clause: 'price > 0',
    });
    throw new ContractViolationError({
      event: 'ProductCreated',
      clause: 'price > 0',
      actual: {
        price,
      },
    });
  }
}

export function validateInventoryUpdatedContract(
  productId: string,
  oldQuantity: number,
  newQuantity: number,
): void {
  if (!((newQuantity >= 0))) {
    console.error('contract_violation', {
      event: 'InventoryUpdated',
      clause: 'newQuantity >= 0',
      newQuantity,
    });
    contractViolationCounter.inc({
      event: 'InventoryUpdated',
      clause: 'newQuantity >= 0',
    });
    throw new ContractViolationError({
      event: 'InventoryUpdated',
      clause: 'newQuantity >= 0',
      actual: {
        newQuantity,
      },
    });
  }
}

export function validateInventoryReservedContract(
  reservationId: string,
  productIds: string[],
): void {
  if (!((productIds.length > 0))) {
    console.error('contract_violation', {
      event: 'InventoryReserved',
      clause: 'productIds.length() > 0',
      productIds,
    });
    contractViolationCounter.inc({
      event: 'InventoryReserved',
      clause: 'productIds.length() > 0',
    });
    throw new ContractViolationError({
      event: 'InventoryReserved',
      clause: 'productIds.length() > 0',
      actual: {
        productIds,
      },
    });
  }
}

export function validateInventoryReleasedContract(
  reservationId: string,
  reason: string,
): void {
  if (!((reason.length > 0))) {
    console.error('contract_violation', {
      event: 'InventoryReleased',
      clause: 'reason.length > 0',
      reason,
    });
    contractViolationCounter.inc({
      event: 'InventoryReleased',
      clause: 'reason.length > 0',
    });
    throw new ContractViolationError({
      event: 'InventoryReleased',
      clause: 'reason.length > 0',
      actual: {
        reason,
      },
    });
  }
}

