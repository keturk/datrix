import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { PaginatedOrders } from '../src/dto/paginated-orders.struct';

describe('PaginatedOrders Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      data: [] as never[],
      pagination: { key: 'value' },
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(PaginatedOrders, payload);
    expect(instance).toBeDefined();
    expect(instance.data).toBeDefined();
    expect(instance.pagination).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(PaginatedOrders, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when data is missing', async () => {
    const payload = buildValidPayload();
    delete payload.data;
    const instance = plainToInstance(PaginatedOrders, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when pagination is missing', async () => {
    const payload = buildValidPayload();
    delete payload.pagination;
    const instance = plainToInstance(PaginatedOrders, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
