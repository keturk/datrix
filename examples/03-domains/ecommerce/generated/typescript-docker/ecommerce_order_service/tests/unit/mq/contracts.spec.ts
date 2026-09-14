/**
 * Tests for event contract validation (auto-generated).
 */
import { Address } from '../../../src/dto/address.struct'
import { OrderStatus } from '../../../src/enums/order-status.enum'
import { validateOrderCreatedContract, validateOrderConfirmedContract, validateOrderCancelledContract, validateOrderStatusChangedContract } from '../../../src/mq/contracts';
import { ContractViolationError } from '../../../src/errors/contract-violation';

describe('OrderCreated contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateOrderCreatedContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
        '00000000-0000-4000-8000-000000000001',
        99.99,
        '00000000-0000-4000-8000-000000000001',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateOrderCreatedContract(
        '00000000-0000-4000-8000-000000000001',
        '',
        '00000000-0000-4000-8000-000000000001',
        99.99,
        '00000000-0000-4000-8000-000000000001',
      ),
    ).toThrow(ContractViolationError);
  });

  it('rejects when clause 1 is violated', () => {
    expect(() =>
      validateOrderCreatedContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
        '00000000-0000-4000-8000-000000000001',
        -1,
        '00000000-0000-4000-8000-000000000001',
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('OrderConfirmed contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateOrderConfirmedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        { street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '+15551234567' },
        [{ key: 'value' }],
        1,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateOrderConfirmedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        { street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '+15551234567' },
        [],
        1,
      ),
    ).toThrow(ContractViolationError);
  });

  it('rejects when clause 1 is violated', () => {
    expect(() =>
      validateOrderConfirmedContract(
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000001',
        { street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '+15551234567' },
        [{ key: 'value' }],
        -1,
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('OrderCancelled contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateOrderCancelledContract(
        '00000000-0000-4000-8000-000000000001',
        'aaaa',
        '00000000-0000-4000-8000-000000000001',
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateOrderCancelledContract(
        '00000000-0000-4000-8000-000000000001',
        '',
        '00000000-0000-4000-8000-000000000001',
      ),
    ).toThrow(ContractViolationError);
  });

});

describe('OrderStatusChanged contracts', () => {
  it('accepts valid payload', () => {
    expect(() =>
      validateOrderStatusChangedContract(
        '00000000-0000-4000-8000-000000000001',
        OrderStatus.Pending,
        OrderStatus.PaymentPending,
      ),
    ).not.toThrow();
  });

  it('rejects when clause 0 is violated', () => {
    expect(() =>
      validateOrderStatusChangedContract(
        '00000000-0000-4000-8000-000000000001',
        OrderStatus.Pending,
        OrderStatus.Pending,
      ),
    ).toThrow(ContractViolationError);
  });

});

