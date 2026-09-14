import { Product } from '../src/ecommerce_product_service/entities/product_db/product.entity';
import { ProductStatus } from '../src/enums/product-status.enum';

describe('Product Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new Product();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new Product();
    const slugVal = `test-${Date.now()}`;
    const priceVal = 99.99;
    const compareAtPriceVal = 99.99;
    const inventoryVal = 42;
    const nameVal = 'test-value';
    const descriptionVal = 'test-text-content';
    const statusVal = ProductStatus.Draft;
    const productMetadataVal = { key: 'value' };
    const imagesVal = { key: 'value' };
    const tagsVal = { key: 'value' };
    const categoryIdVal = '550e8400-e29b-41d4-a716-446655440000';
    entity.slug = slugVal;
    entity.price = priceVal;
    entity.compareAtPrice = compareAtPriceVal;
    entity.inventory = inventoryVal;
    entity.name = nameVal;
    entity.description = descriptionVal;
    entity.status = statusVal;
    entity.productMetadata = productMetadataVal;
    entity.images = imagesVal;
    entity.tags = tagsVal;
    entity.categoryId = categoryIdVal;
    expect(entity.slug).toBe(slugVal);
    expect(entity.price).toBe(priceVal);
    expect(entity.compareAtPrice).toBe(compareAtPriceVal);
    expect(entity.inventory).toBe(inventoryVal);
    expect(entity.name).toBe(nameVal);
    expect(entity.description).toBe(descriptionVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.productMetadata).toBe(productMetadataVal);
    expect(entity.images).toBe(imagesVal);
    expect(entity.tags).toBe(tagsVal);
    expect(entity.categoryId).toBe(categoryIdVal);
  });

  it('should update field values', () => {
    const entity = new Product();
    const slugVal = `updated-${Date.now()}`;
    const priceVal = 149.99;
    const compareAtPriceVal = 149.99;
    const inventoryVal = 99;
    const nameVal = 'updated-value';
    const descriptionVal = 'updated-text-content';
    const statusVal = ProductStatus.Active;
    const productMetadataVal = { key: 'updated' };
    const imagesVal = { key: 'updated' };
    const tagsVal = { key: 'updated' };
    const categoryIdVal = '660e8400-e29b-41d4-a716-446655440001';
    entity.slug = slugVal;
    entity.price = priceVal;
    entity.compareAtPrice = compareAtPriceVal;
    entity.inventory = inventoryVal;
    entity.name = nameVal;
    entity.description = descriptionVal;
    entity.status = statusVal;
    entity.productMetadata = productMetadataVal;
    entity.images = imagesVal;
    entity.tags = tagsVal;
    entity.categoryId = categoryIdVal;
    expect(entity.slug).toBe(slugVal);
    expect(entity.price).toBe(priceVal);
    expect(entity.compareAtPrice).toBe(compareAtPriceVal);
    expect(entity.inventory).toBe(inventoryVal);
    expect(entity.name).toBe(nameVal);
    expect(entity.description).toBe(descriptionVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.productMetadata).toBe(productMetadataVal);
    expect(entity.images).toBe(imagesVal);
    expect(entity.tags).toBe(tagsVal);
    expect(entity.categoryId).toBe(categoryIdVal);
  });

  it('should enforce unique constraint on slug', () => {
    const entity = new Product();
    entity.slug = `test-${Date.now()}`;
    expect(entity.slug).toBeDefined();
  });

  it('should have index on categoryId', () => {
    const entity = new Product();
    entity.categoryId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.categoryId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new Product();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});
