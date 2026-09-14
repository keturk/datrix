/**
 * Tests for event contract validation (auto-generated).
 */
import { validateProcessPaymentContract, validateSendOrderConfirmationContract, validateSettlePaymentContract } from '../../../src/queue/contracts';
import { ContractViolationError } from '../../../src/errors/contract-violation';

describe('ProcessPayment contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateProcessPaymentContract(
        '00000000-0000-4000-8000-000000000001',
        99.99,
        'aaa',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateProcessPaymentContract(
        '00000000-0000-4000-8000-000000000001',
        -1,
        'aaa',
      ),
    ).toThrow(ContractViolationError);
  });

  it('rejects when clause 1 is violated', () => {
    expect(() =>
      validateProcessPaymentContract(
        '00000000-0000-4000-8000-000000000001',
        99.99,
        '',
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('SendOrderConfirmation contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateSendOrderConfirmationContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaaaaaaaaaaaaaa',
        'test',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateSendOrderConfirmationContract(
        '00000000-0000-4000-8000-000000000001',
        '',
        'test',
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('SettlePayment contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateSettlePaymentContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
        1,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateSettlePaymentContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
        -1,
      ),
    ).toThrow(ContractViolationError);
  });

  it('rejects when clause 1 is violated', () => {
    expect(() =>
      validateSettlePaymentContract(
        '00000000-0000-4000-8000-000000000001',
        '',
        1,
      ),
    ).toThrow(ContractViolationError);
  });

});

