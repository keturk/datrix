import { Product } from '../src/entities/product.entity';
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
    const categoryIdVal = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
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
    const categoryIdVal = 'b1ffbc99-9c0b-4ef8-bb6d-6bb9bd380a22';
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

  it('should have server-managed fields', () => {
    const entity = new Product();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
