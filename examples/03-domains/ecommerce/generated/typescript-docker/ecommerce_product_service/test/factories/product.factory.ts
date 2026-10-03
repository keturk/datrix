import { Product } from '../../src/entities/product.entity';

/**
 * Build a partial Product with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildProduct(
  overrides?: Partial<Product>,
): Partial<Product> {
  return {
    slug: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    price: 99.99,
    compareAtPrice: 99.99,
    name: 'test',
    description: 'test',
    productMetadata: { key: 'value' },
    images: { key: 'value' },
    tags: { key: 'value' },
    category: crypto.randomUUID(),
    ...overrides,
  };
}
