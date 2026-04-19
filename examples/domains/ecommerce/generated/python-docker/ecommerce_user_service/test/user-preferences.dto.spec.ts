import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateUserPreferencesDto } from '../src/dto/create-user-preferences.dto';

describe('CreateUserPreferencesDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      language: 'test-value',
      timezone: 'test-value',
      emailNotifications: true,
      smsNotifications: true,
      preferences: { key: 'value' },
      userId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateUserPreferencesDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when preferences is missing', async () => {
    const payload = buildValidPayload();
    delete payload.preferences;
    const dto = plainToInstance(CreateUserPreferencesDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'preferences');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when userId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.userId;
    const dto = plainToInstance(CreateUserPreferencesDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'userId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when language exceeds max length 10', async () => {
    const payload = buildValidPayload();
    payload.language = 'x'.repeat(10 + 1);
    const dto = plainToInstance(CreateUserPreferencesDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'language');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when timezone exceeds max length 50', async () => {
    const payload = buildValidPayload();
    payload.timezone = 'x'.repeat(50 + 1);
    const dto = plainToInstance(CreateUserPreferencesDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'timezone');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});
