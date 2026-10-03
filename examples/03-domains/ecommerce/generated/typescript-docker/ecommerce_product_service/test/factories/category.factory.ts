import { Category } from '../../src/entities/category.entity';

/**
 * Build a partial Category with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildCategory(
  overrides?: Partial<Category>,
): Partial<Category> {
  return {
    name: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    description: 'test',
    slug: `test-${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    ...overrides,
  };
}
