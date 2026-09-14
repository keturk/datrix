import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { PaginationResult } from '../src/dto/pagination-result.struct';

describe('PaginationResult Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      page: 42,
      perPage: 42,
      total: 42,
      totalPages: 42,
      hasNext: true,
      hasPrev: true,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(PaginationResult, payload);
    expect(instance).toBeDefined();
    expect(instance.page).toBeDefined();
    expect(instance.perPage).toBeDefined();
    expect(instance.total).toBeDefined();
    expect(instance.totalPages).toBeDefined();
    expect(instance.hasNext).toBeDefined();
    expect(instance.hasPrev).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(PaginationResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when page is missing', async () => {
    const payload = buildValidPayload();
    delete payload.page;
    const instance = plainToInstance(PaginationResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when perPage is missing', async () => {
    const payload = buildValidPayload();
    delete payload.perPage;
    const instance = plainToInstance(PaginationResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when total is missing', async () => {
    const payload = buildValidPayload();
    delete payload.total;
    const instance = plainToInstance(PaginationResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when totalPages is missing', async () => {
    const payload = buildValidPayload();
    delete payload.totalPages;
    const instance = plainToInstance(PaginationResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when hasNext is missing', async () => {
    const payload = buildValidPayload();
    delete payload.hasNext;
    const instance = plainToInstance(PaginationResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when hasPrev is missing', async () => {
    const payload = buildValidPayload();
    delete payload.hasPrev;
    const instance = plainToInstance(PaginationResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
