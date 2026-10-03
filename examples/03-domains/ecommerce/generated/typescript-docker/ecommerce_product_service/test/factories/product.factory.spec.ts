import { buildProduct } from './product.factory';

describe('buildProduct', () => {
  it('should return a valid partial entity', () => {
    const result = buildProduct();
    expect(result).toBeDefined();
    expect(result.slug).toBeDefined();
    expect(result.price).toBeDefined();
    expect(result.compareAtPrice).toBeDefined();
    expect(result.name).toBeDefined();
    expect(result.description).toBeDefined();
    expect(result.productMetadata).toBeDefined();
    expect(result.images).toBeDefined();
    expect(result.tags).toBeDefined();
    expect(result.category).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      slug: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    };
    const result = buildProduct(overrides);
    expect(result.slug).toBe(overrides.slug);
  });

  it('should produce different instances', () => {
    const a = buildProduct();
    const b = buildProduct();
    expect(a).not.toBe(b);
  });
});
