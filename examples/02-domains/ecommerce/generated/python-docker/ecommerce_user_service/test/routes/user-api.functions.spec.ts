import { Test, TestingModule } from '@nestjs/testing';
import { UserApiController } from '../../src/controllers/user-api.controller';

describe('UserApi Functions', () => {
  let controller: UserApiController;

  beforeAll(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [UserApiController],
    }).compile();

    controller = module.get<UserApiController>(UserApiController);
  });

  describe('generateSessionToken', () => {
    it('should be defined', () => {
      expect(controller.generateSessionToken).toBeDefined();
    });

    it('should return a value', async () => {
      const result = await controller.generateSessionToken();
      expect(result).toBeDefined();
    });
  });

});
