/**
 * Tests for event contract validation (auto-generated).
 */
import { validateShipmentDispatchedContract, validateShipmentFailedContract } from '../../../src/mq/contracts';
import { ContractViolationError } from '../../../src/errors/contract-violation';

describe('ShipmentDispatched contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateShipmentDispatchedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateShipmentDispatchedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        '',
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('ShipmentFailed contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateShipmentFailedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateShipmentFailedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        '',
      ),
    ).toThrow(ContractViolationError);
  });

});

