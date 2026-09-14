/**
 * Tests for event contract validation (auto-generated).
 */
import { validateProductCreatedContract, validateInventoryUpdatedContract, validateInventoryReservedContract, validateInventoryReleasedContract } from '../../../src/mq/contracts';
import { ContractViolationError } from '../../../src/errors/contract-violation';

describe('ProductCreated contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateProductCreatedContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
        99.99,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateProductCreatedContract(
        '00000000-0000-4000-8000-000000000001',
        '',
        99.99,
      ),
    ).toThrow(ContractViolationError);
  });

  it('rejects when clause 1 is violated', () => {
    expect(() =>
      validateProductCreatedContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
        -1,
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('InventoryUpdated contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateInventoryUpdatedContract(
        '00000000-0000-4000-8000-000000000001',
        1,
        1,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateInventoryUpdatedContract(
        '00000000-0000-4000-8000-000000000001',
        1,
        -1,
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('InventoryReserved contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateInventoryReservedContract(
        '00000000-0000-4000-8000-000000000001',
        ['00000000-0000-4000-8000-000000000001'],
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateInventoryReservedContract(
        '00000000-0000-4000-8000-000000000001',
        [],
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('InventoryReleased contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateInventoryReleasedContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateInventoryReleasedContract(
        '00000000-0000-4000-8000-000000000001',
        '',
      ),
    ).toThrow(ContractViolationError);
  });

});

