import {
  Entity,
  Property,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_notification_audits_order_id', properties: ['orderId'] })
@Entity({ tableName: 'notification_audits' })
export class NotificationAudit extends BaseEntity {
  [OptionalProps]?: "createdAt" | "id" | "updatedAt";


  @Property({ columnType: 'uuid', fieldName: 'order_id' })
  orderId!: string;

  @Property({ columnType: 'varchar', fieldName: 'recipient_email' })
  recipientEmail!: string;

  @Property({ columnType: 'varchar', fieldName: 'order_number' })
  orderNumber!: string;





}
