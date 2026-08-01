import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { Pagination } from '../src/dto/pagination.struct';

describe('Pagination Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      page: 42,
      perPage: 42,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(Pagination, payload);
    expect(instance).toBeDefined();
    expect(instance.page).toBeDefined();
    expect(instance.perPage).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(Pagination, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should have computed field offset', () => {
    const instance = new Pagination();
    expect('offset' in instance).toBe(true);
  });

});
