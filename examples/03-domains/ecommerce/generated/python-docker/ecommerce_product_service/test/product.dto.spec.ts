import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateProductDto } from '../src/dto/create-product.dto';
import { ProductStatus } from '../src/enums/product-status.enum';

describe('CreateProductDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      slug: `test-${Date.now()}`,
      price: 99.99,
      compareAtPrice: 99.99,
      inventory: 42,
      name: 'test-value',
      description: 'test-text-content',
      status: ProductStatus.Draft,
      productMetadata: { key: 'value' },
      images: { key: 'value' },
      tags: { key: 'value' },
      categoryId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when slug is missing', async () => {
    const payload = buildValidPayload();
    delete payload.slug;
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'slug');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when price is missing', async () => {
    const payload = buildValidPayload();
    delete payload.price;
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'price');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when name is missing', async () => {
    const payload = buildValidPayload();
    delete payload.name;
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'name');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when description is missing', async () => {
    const payload = buildValidPayload();
    delete payload.description;
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'description');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when images is missing', async () => {
    const payload = buildValidPayload();
    delete payload.images;
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'images');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when tags is missing', async () => {
    const payload = buildValidPayload();
    delete payload.tags;
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'tags');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when categoryId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.categoryId;
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'categoryId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when slug exceeds max length 200', async () => {
    const payload = buildValidPayload();
    payload.slug = 'x'.repeat(200 + 1);
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'slug');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when name exceeds max length 200', async () => {
    const payload = buildValidPayload();
    payload.name = 'x'.repeat(200 + 1);
    const dto = plainToInstance(CreateProductDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'name');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});
