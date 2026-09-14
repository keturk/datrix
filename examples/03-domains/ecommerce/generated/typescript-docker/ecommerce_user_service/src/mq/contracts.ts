/**
 * Event contract validation (auto-generated).
 */
import { ContractViolationError } from '../errors/contract-violation';
import { contractViolationCounter } from './contract-metrics';
import { UserStatus } from '../enums/user-status.enum'

export function validateUserRegisteredContract(
  userId: string,
  email: string,
  fullName: string,
): void {
  if (!((fullName.length > 0))) {
    console.error('contract_violation', {
      event: 'UserRegistered',
      clause: 'fullName.length > 0',
      fullName,
    });
    contractViolationCounter.inc({
      event: 'UserRegistered',
      clause: 'fullName.length > 0',
    });
    throw new ContractViolationError({
      event: 'UserRegistered',
      clause: 'fullName.length > 0',
      actual: {
        fullName,
      },
    });
  }
}

export function validateUserStatusChangedContract(
  userId: string,
  oldStatus: UserStatus,
  newStatus: UserStatus,
): void {
  if (!((oldStatus !== newStatus))) {
    console.error('contract_violation', {
      event: 'UserStatusChanged',
      clause: 'oldStatus != newStatus',
      newStatus,
      oldStatus,
    });
    contractViolationCounter.inc({
      event: 'UserStatusChanged',
      clause: 'oldStatus != newStatus',
    });
    throw new ContractViolationError({
      event: 'UserStatusChanged',
      clause: 'oldStatus != newStatus',
      actual: {
        newStatus,
        oldStatus,
      },
    });
  }
}

