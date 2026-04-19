import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateCategoryDto } from '../src/dto/create-category.dto';

describe('CreateCategoryDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      name: `test-${Date.now()}`,
      description: 'test-text-content',
      slug: `test-${Date.now()}`,
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateCategoryDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when name is missing', async () => {
    const payload = buildValidPayload();
    delete payload.name;
    const dto = plainToInstance(CreateCategoryDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'name');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when slug is missing', async () => {
    const payload = buildValidPayload();
    delete payload.slug;
    const dto = plainToInstance(CreateCategoryDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'slug');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when name exceeds max length 100', async () => {
    const payload = buildValidPayload();
    payload.name = 'x'.repeat(100 + 1);
    const dto = plainToInstance(CreateCategoryDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'name');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});
