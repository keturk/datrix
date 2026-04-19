import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateProductRequest } from '../src/dto/create-product-request.struct';

describe('CreateProductRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      name: 'test-value',
      description: 'test-text-content',
      price: 99.99,
      categoryId: '550e8400-e29b-41d4-a716-446655440000',
      inventory: 42,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateProductRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.name).toBeDefined();
    expect(instance.description).toBeDefined();
    expect(instance.price).toBeDefined();
    expect(instance.categoryId).toBeDefined();
    expect(instance.inventory).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateProductRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when name is missing', async () => {
    const payload = buildValidPayload();
    delete payload.name;
    const instance = plainToInstance(CreateProductRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when description is missing', async () => {
    const payload = buildValidPayload();
    delete payload.description;
    const instance = plainToInstance(CreateProductRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when price is missing', async () => {
    const payload = buildValidPayload();
    delete payload.price;
    const instance = plainToInstance(CreateProductRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when categoryId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.categoryId;
    const instance = plainToInstance(CreateProductRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
