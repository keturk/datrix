import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('UserController', () => {
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

  describe('GET /api/v1/users', () => {
    it('should return a list of users', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/users')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(response.body).toBeInstanceOf(Array);
    });
  });

  describe('GET /api/v1/users/:id', () => {
    it('should return a single user', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });

    it('should return 404 for non-existent user', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/users/00000000-0000-0000-0000-000000000099')
        .set('Authorization', 'Bearer test-token')
        .expect(404);
    });
  });

  describe('POST /api/v1/users', () => {
    it('should create a new user', async () => {
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

      const response = await request(app.getHttpServer())
        .post('/api/v1/users')
        .set('Authorization', 'Bearer test-token')
        .send(createDto)
        .expect(201);

      expect(response.body).toHaveProperty('id');
      expect(response.body.createdAt).toBeDefined();
      expect(response.body.updatedAt).toBeDefined();
      expect(response.body.email).toBeDefined();
      expect(response.body.firstName).toBeDefined();
      expect(response.body.lastName).toBeDefined();
      expect(response.body.phoneNumber).toBeDefined();
      expect(response.body.role).toBeDefined();
      expect(response.body.status).toBeDefined();
      expect(response.body.lastLoginAt).toBeDefined();
      expect(response.body.emailVerifiedAt).toBeDefined();
      expect(response.body.emailVerificationToken).toBeDefined();
      expect(response.body.passwordResetToken).toBeDefined();
      expect(response.body.passwordResetExpiry).toBeDefined();
      expect(response.body.shippingAddress).toBeDefined();
      expect(response.body.billingAddress).toBeDefined();
    });
  });

  describe('PATCH /api/v1/users/:id', () => {
    it('should update an existing user', async () => {
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

      const response = await request(app.getHttpServer())
        .patch('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .send(updateDto)
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });
  });

  describe('DELETE /api/v1/users/:id', () => {
    it('should delete an existing user', async () => {
      await request(app.getHttpServer())
        .delete('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(204);
    });
  });

});
