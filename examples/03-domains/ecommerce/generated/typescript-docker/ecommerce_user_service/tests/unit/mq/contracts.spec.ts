/**
 * Tests for event contract validation (auto-generated).
 */
import { UserStatus } from '../../../src/enums/user-status.enum'
import { validateUserRegisteredContract, validateUserStatusChangedContract } from '../../../src/mq/contracts';
import { ContractViolationError } from '../../../src/errors/contract-violation';

describe('UserRegistered contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateUserRegisteredContract(
        '00000000-0000-4000-8000-000000000001',
        'user@example.com',
        'aaaa',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateUserRegisteredContract(
        '00000000-0000-4000-8000-000000000001',
        'user@example.com',
        '',
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('UserStatusChanged contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateUserStatusChangedContract(
        '00000000-0000-4000-8000-000000000001',
        UserStatus.Active,
        UserStatus.Inactive,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateUserStatusChangedContract(
        '00000000-0000-4000-8000-000000000001',
        UserStatus.Active,
        UserStatus.Active,
      ),
    ).toThrow(ContractViolationError);
  });

});

