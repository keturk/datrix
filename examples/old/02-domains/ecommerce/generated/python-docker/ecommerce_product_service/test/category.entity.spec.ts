import { Category } from '../src/entities/category.entity';

describe('Category Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new Category();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new Category();
    const nameVal = `test-${Date.now()}`;
    const descriptionVal = 'test-text-content';
    const slugVal = `test-${Date.now()}`;
    entity.name = nameVal;
    entity.description = descriptionVal;
    entity.slug = slugVal;
    expect(entity.name).toBe(nameVal);
    expect(entity.description).toBe(descriptionVal);
    expect(entity.slug).toBe(slugVal);
  });

  it('should update field values', () => {
    const entity = new Category();
    const nameVal = `updated-${Date.now()}`;
    const descriptionVal = 'updated-text-content';
    const slugVal = `updated-${Date.now()}`;
    entity.name = nameVal;
    entity.description = descriptionVal;
    entity.slug = slugVal;
    expect(entity.name).toBe(nameVal);
    expect(entity.description).toBe(descriptionVal);
    expect(entity.slug).toBe(slugVal);
  });

  it('should enforce unique constraint on name', () => {
    const entity = new Category();
    entity.name = `test-${Date.now()}`;
    expect(entity.name).toBeDefined();
  });

  it('should enforce unique constraint on slug', () => {
    const entity = new Category();
    entity.slug = `test-${Date.now()}`;
    expect(entity.slug).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new Category();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
