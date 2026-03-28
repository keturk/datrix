import { Product } from '../../src/entities/product.entity';
import { ProductStatus } from '../../src/enums/product-status.enum';

/**
 * Build a partial Product with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildProduct(
  overrides?: Partial<Product>,
): Partial<Product> {
  return {
    slug: `x`,
    price: 99.99,
    compareAtPrice: 99.99,
    inventory: 42,
    name: `x`,
    description: 'test-text-content',
    status: ProductStatus.Draft,
    productMetadata: {},
    images: {},
    tags: {},
    categoryId: crypto.randomUUID(),
    ...overrides,
  };
}
