import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('UserController Integration', () => {
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

  it('should create and retrieve a user', async () => {
    const createDto = {
      createdAt: new Date(),
      updatedAt: new Date(),
      email: "user@test.invalid",
      passwordHash: "********",
      firstName: 'test_value',
      lastName: 'test_value',
      phoneNumber: 'test_value',
      role: 'test_value',
      status: 'test_value',
      lastLoginAt: 'test_value',
      emailVerifiedAt: 'test_value',
      emailVerificationToken: 'test_value',
      passwordResetToken: 'test_value',
      passwordResetExpiry: 'test_value',
      shippingAddress: 'test_value',
      billingAddress: 'test_value',
    };

    const createResponse = await request(app.getHttpServer())
      .post('/api/v1/users')
      .set('Authorization', 'Bearer test-token')
      .send(createDto)
      .expect(201);

    const id = createResponse.body.id;

    const getResponse = await request(app.getHttpServer())
      .get(`/api/v1/users/${id}`)
      .set('Authorization', 'Bearer test-token')
      .expect(200);

    expect(getResponse.body.id).toBe(id);
  });

  it('should create and update a user', async () => {
    const createDto = {
      createdAt: new Date(),
      updatedAt: new Date(),
      email: "user@test.invalid",
      passwordHash: "********",
      firstName: 'test_value',
      lastName: 'test_value',
      phoneNumber: 'test_value',
      role: 'test_value',
      status: 'test_value',
      lastLoginAt: 'test_value',
      emailVerifiedAt: 'test_value',
      emailVerificationToken: 'test_value',
      passwordResetToken: 'test_value',
      passwordResetExpiry: 'test_value',
      shippingAddress: 'test_value',
      billingAddress: 'test_value',
    };

    const createResponse = await request(app.getHttpServer())
      .post('/api/v1/users')
      .set('Authorization', 'Bearer test-token')
      .send(createDto)
      .expect(201);

    const id = createResponse.body.id;

    const updateDto = {
      createdAt: new Date(),
      updatedAt: new Date(),
      email: "user@test.invalid",
      passwordHash: "********",
      firstName: 'test_value',
      lastName: 'test_value',
      phoneNumber: 'test_value',
      role: 'test_value',
      status: 'test_value',
      lastLoginAt: 'test_value',
      emailVerifiedAt: 'test_value',
      emailVerificationToken: 'test_value',
      passwordResetToken: 'test_value',
      passwordResetExpiry: 'test_value',
      shippingAddress: 'test_value',
      billingAddress: 'test_value',
    };

    await request(app.getHttpServer())
      .patch(`/api/v1/users/${id}`)
      .set('Authorization', 'Bearer test-token')
      .send(updateDto)
      .expect(200);
  });

  it('should create and delete a user', async () => {
    const createDto = {
      createdAt: new Date(),
      updatedAt: new Date(),
      email: "user@test.invalid",
      passwordHash: "********",
      firstName: 'test_value',
      lastName: 'test_value',
      phoneNumber: 'test_value',
      role: 'test_value',
      status: 'test_value',
      lastLoginAt: 'test_value',
      emailVerifiedAt: 'test_value',
      emailVerificationToken: 'test_value',
      passwordResetToken: 'test_value',
      passwordResetExpiry: 'test_value',
      shippingAddress: 'test_value',
      billingAddress: 'test_value',
    };

    const createResponse = await request(app.getHttpServer())
      .post('/api/v1/users')
      .set('Authorization', 'Bearer test-token')
      .send(createDto)
      .expect(201);

    const id = createResponse.body.id;

    await request(app.getHttpServer())
      .delete(`/api/v1/users/${id}`)
      .set('Authorization', 'Bearer test-token')
      .expect(204);
  });

});
