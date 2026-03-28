import { Order } from '../src/entities/order.entity';

describe('Order Functions', () => {
  describe('calculateTotals', () => {
    it('should be defined as a method', () => {
      const entity = new Order();
      expect(typeof entity.calculateTotals).toBe('function');
    });

    it('should accept 0 parameter(s)', () => {
      const entity = new Order();
      expect(entity.calculateTotals.length).toBe(0);
    });

  });

});
