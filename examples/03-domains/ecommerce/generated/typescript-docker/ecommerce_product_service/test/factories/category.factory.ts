import { Category } from '../../src/entities/category.entity';

/**
 * Build a partial Category with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildCategory(
  overrides?: Partial<Category>,
): Partial<Category> {
  return {
    name: `x`,
    description: 'test-text-content',
    slug: `test-${Date.now()}`,
    ...overrides,
  };
}
