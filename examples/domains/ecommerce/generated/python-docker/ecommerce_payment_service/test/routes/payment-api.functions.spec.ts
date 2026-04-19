import { Test, TestingModule } from '@nestjs/testing';
import { PaymentApiController } from '../../src/controllers/payment-api.controller';

describe('PaymentApi Functions', () => {
  let controller: PaymentApiController;

  beforeAll(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [PaymentApiController],
    }).compile();

    controller = module.get<PaymentApiController>(PaymentApiController);
  });

  describe('processRefundViaGateway', () => {
    it('should be defined', () => {
      expect(controller.processRefundViaGateway).toBeDefined();
    });

    it('should return a value', async () => {
      const result = await controller.processRefundViaGateway(undefined, undefined);
      expect(result).toBeDefined();
    });
  });

});
