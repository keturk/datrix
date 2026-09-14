import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateNotificationAuditDto } from '../src/dto/create-notification-audit.dto';

describe('CreateNotificationAuditDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      orderId: '550e8400-e29b-41d4-a716-446655440000',
      recipientEmail: 'user@example.com',
      orderNumber: 'test-value',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateNotificationAuditDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when orderId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderId;
    const dto = plainToInstance(CreateNotificationAuditDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'orderId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when recipientEmail is missing', async () => {
    const payload = buildValidPayload();
    delete payload.recipientEmail;
    const dto = plainToInstance(CreateNotificationAuditDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'recipientEmail');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when orderNumber is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderNumber;
    const dto = plainToInstance(CreateNotificationAuditDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'orderNumber');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when orderNumber exceeds max length 64', async () => {
    const payload = buildValidPayload();
    payload.orderNumber = 'x'.repeat(64 + 1);
    const dto = plainToInstance(CreateNotificationAuditDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'orderNumber');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});
