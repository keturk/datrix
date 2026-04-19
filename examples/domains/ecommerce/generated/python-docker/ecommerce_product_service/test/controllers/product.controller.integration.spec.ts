import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ProductController Integration', () => {
  let app: INestApplication;

  beforeAll(async () => {
    process.env.JWT_SECRET = 'datrix-test-jwt-secret';
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

  it('should create and retrieve a product', async () => {
    const createDto = {
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
    };

    const createResponse = await request(app.getHttpServer())
      .post('/api/v1/products/products')
      .set('Authorization', 'Bearer test-token')
      .send(createDto)
      .expect(201);

    const id = createResponse.body.id;

    const getResponse = await request(app.getHttpServer())
      .get(`/api/v1/products/products/${id}`)
      .set('Authorization', 'Bearer test-token')
      .expect(200);

    expect(getResponse.body.id).toBe(id);
  });

  it('should create and update a product', async () => {
    const createDto = {
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
    };

    const createResponse = await request(app.getHttpServer())
      .post('/api/v1/products/products')
      .set('Authorization', 'Bearer test-token')
      .send(createDto)
      .expect(201);

    const id = createResponse.body.id;

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
    };

    await request(app.getHttpServer())
      .patch(`/api/v1/products/products/${id}`)
      .set('Authorization', 'Bearer test-token')
      .send(updateDto)
      .expect(200);
  });

  it('should create and delete a product', async () => {
    const createDto = {
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
    };

    const createResponse = await request(app.getHttpServer())
      .post('/api/v1/products/products')
      .set('Authorization', 'Bearer test-token')
      .send(createDto)
      .expect(201);

    const id = createResponse.body.id;

    await request(app.getHttpServer())
      .delete(`/api/v1/products/products/${id}`)
      .set('Authorization', 'Bearer test-token')
      .expect(204);
  });

});
