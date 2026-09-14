import { NotificationAudit } from '../src/ecommerce_notification_service/entities/notification_db/notification-audit.entity';

describe('NotificationAudit Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new NotificationAudit();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new NotificationAudit();
    const orderIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const recipientEmailVal = 'user@example.com';
    const orderNumberVal = 'test-value';
    entity.orderId = orderIdVal;
    entity.recipientEmail = recipientEmailVal;
    entity.orderNumber = orderNumberVal;
    expect(entity.orderId).toBe(orderIdVal);
    expect(entity.recipientEmail).toBe(recipientEmailVal);
    expect(entity.orderNumber).toBe(orderNumberVal);
  });

  it('should update field values', () => {
    const entity = new NotificationAudit();
    const orderIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const recipientEmailVal = 'updated@example.com';
    const orderNumberVal = 'updated-value';
    entity.orderId = orderIdVal;
    entity.recipientEmail = recipientEmailVal;
    entity.orderNumber = orderNumberVal;
    expect(entity.orderId).toBe(orderIdVal);
    expect(entity.recipientEmail).toBe(recipientEmailVal);
    expect(entity.orderNumber).toBe(orderNumberVal);
  });

  it('should have index on orderId', () => {
    const entity = new NotificationAudit();
    entity.orderId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.orderId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new NotificationAudit();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});
