import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { UpdateUserStatusRequest } from '../src/dto/update-user-status-request.struct';
import { UserStatus } from '../src/enums/user-status.enum';

describe('UpdateUserStatusRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      status: UserStatus.Active,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateUserStatusRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.status).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateUserStatusRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when status is missing', async () => {
    const payload = buildValidPayload();
    delete payload.status;
    const instance = plainToInstance(UpdateUserStatusRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
