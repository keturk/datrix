import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateUserSessionDto } from '../src/dto/create-user-session.dto';

describe('CreateUserSessionDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      token: `test-${Date.now()}`,
      deviceName: 'test-value',
      ipAddress: '192.168.1.1',
      userAgent: 'test-value',
      expiresAt: new Date('2025-01-15T12:00:00Z'),
      lastActivityAt: new Date('2025-01-15T12:00:00Z'),
      userId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateUserSessionDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when token is missing', async () => {
    const payload = buildValidPayload();
    delete payload.token;
    const dto = plainToInstance(CreateUserSessionDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'token');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when expiresAt is missing', async () => {
    const payload = buildValidPayload();
    delete payload.expiresAt;
    const dto = plainToInstance(CreateUserSessionDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'expiresAt');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when userId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.userId;
    const dto = plainToInstance(CreateUserSessionDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'userId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when token exceeds max length 255', async () => {
    const payload = buildValidPayload();
    payload.token = 'x'.repeat(255 + 1);
    const dto = plainToInstance(CreateUserSessionDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'token');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when deviceName exceeds max length 500', async () => {
    const payload = buildValidPayload();
    payload.deviceName = 'x'.repeat(500 + 1);
    const dto = plainToInstance(CreateUserSessionDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'deviceName');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when userAgent exceeds max length 255', async () => {
    const payload = buildValidPayload();
    payload.userAgent = 'x'.repeat(255 + 1);
    const dto = plainToInstance(CreateUserSessionDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'userAgent');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});
