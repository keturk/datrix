import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ProductController', () => {
  let app: INestApplication;

  beforeAll(async () => {
    process.env.NODE_ENV = 'test';
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  describe('GET /api/v1/products/products', () => {
    it('should return a list of products', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/products/products')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(response.body).toBeInstanceOf(Array);
    });
  });

  describe('GET /api/v1/products/products/:id', () => {
    it('should return a single product', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/products/products/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });

    it('should return 404 for non-existent product', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/products/products/00000000-0000-0000-0000-000000000099')
        .set('Authorization', 'Bearer test-token')
        .expect(404);
    });
  });

  describe('PATCH /api/v1/products/products/:id', () => {
    it('should update an existing product', async () => {
      const updateDto = {
        createdAt: new Date(),
        updatedAt: new Date(),
        slug: 'test_value',
        price: 19.99,
        compareAtPrice: 'test_value',
        inventory: 1,
        name: 'test_value',
        description: "test_value",
        status: 'test_value',
        productMetadata: 'test_value',
        images: {"key": "value"},
        tags: {"key": "value"},
        categoryId: '00000000-0000-0000-0000-000000000001',
      };

      const response = await request(app.getHttpServer())
        .patch('/api/v1/products/products/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .send(updateDto)
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });
  });

  describe('DELETE /api/v1/products/products/:id', () => {
    it('should delete an existing product', async () => {
      await request(app.getHttpServer())
        .delete('/api/v1/products/products/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(204);
    });
  });

});
