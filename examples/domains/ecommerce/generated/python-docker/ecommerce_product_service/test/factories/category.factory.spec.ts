import { buildCategory } from './category.factory';

describe('buildCategory', () => {
  it('should return a valid partial entity', () => {
    const result = buildCategory();
    expect(result).toBeDefined();
    expect(result.name).toBeDefined();
    expect(result.description).toBeDefined();
    expect(result.slug).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      name: `x`,
    };
    const result = buildCategory(overrides);
    expect(result.name).toBe(overrides.name);
  });

  it('should produce different instances', () => {
    const a = buildCategory();
    const b = buildCategory();
    expect(a).not.toBe(b);
  });
});
