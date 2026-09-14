/**
 * Tests for event contract validation (auto-generated).
 */
import { validatePaymentProcessedContract, validatePaymentFailedContract, validatePaymentRefundedContract } from '../../../src/mq/contracts';
import { ContractViolationError } from '../../../src/errors/contract-violation';

describe('PaymentProcessed contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validatePaymentProcessedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        99.99,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validatePaymentProcessedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        -1,
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('PaymentFailed contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validatePaymentFailedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validatePaymentFailedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        '',
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('PaymentRefunded contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validatePaymentRefundedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        99.99,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validatePaymentRefundedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        -1,
      ),
    ).toThrow(ContractViolationError);
  });

});

