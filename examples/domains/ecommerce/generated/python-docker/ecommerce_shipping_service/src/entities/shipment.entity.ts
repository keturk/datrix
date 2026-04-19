import {
  Entity,
  Column,
  OneToMany,
  Index,
  BeforeInsert,
  BeforeUpdate,
  BeforeRemove,
  AfterInsert,
  AfterUpdate,
  AfterRemove,
  AfterLoad,
} from 'typeorm';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { Address } from '../dto/address.struct'
import { ShipmentDeliveredEvent } from '../events/shipment-delivered.event';
import { ShipmentDispatchedEvent } from '../events/shipment-dispatched.event';
import { ShipmentFailedEvent } from '../events/shipment-failed.event';
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';
import { differenceInDays } from 'date-fns';

import { ShipmentEvent } from './shipment-event.entity';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index('idx_shipments_order_id', ['orderId'])
@Index('idx_shipments_carrier_status', ['carrier', 'status'])
@Entity('shipments')
export class Shipment extends BaseEntity {
  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('typeorm').EntityManager;

  @Column({
    type: 'uuid',
  })
  orderId!: string;

  @Column({
    type: 'varchar',
    unique: true,
  })
  trackingNumber!: string;

  @Column({
    type: 'enum',
    enum: ShippingCarrier,
  })
  carrier!: ShippingCarrier;

  @Column({
    type: 'enum',
    default: ShipmentStatus.Pending,
    enum: ShipmentStatus,
  })
  status!: ShipmentStatus;

  @Column({
    type: 'jsonb',
  })
  destination!: Address;

  @Column({
    type: 'decimal',
  })
  weight!: number;

  @Column({
    type: 'timestamp',
    nullable: true,
  })
  estimatedDelivery?: Date | null;

  @Column({
    type: 'timestamp',
    nullable: true,
  })
  actualDelivery?: Date | null;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  failureReason?: string | null;


  @OneToMany(() => ShipmentEvent, (shipmentevent) => shipmentevent.shipment)
  events!: ShipmentEvent[];

  isDelivered!: boolean;
  isInProgress!: boolean;
  daysInTransit!: number;

  @AfterLoad()
  _hydrateComputed(): void {
    this.isDelivered = (this.status === ShipmentStatus.Delivered);
    this.isInProgress = ((this.status === ShipmentStatus.InTransit) || (this.status === ShipmentStatus.OutForDelivery));
    this.daysInTransit = this.calculateDaysInTransit();
  }

  calculateDaysInTransit(): number {
    if ((this.actualDelivery == null)) {
      return 0;
    }
    return differenceInDays(this.createdAt, this.actualDelivery!);
  }

  markDelivered(): void {
    this.status = ShipmentStatus.Delivered;
    this.actualDelivery = new Date();
    this.save();
  }

  markFailed(reason: string): void {
    this.status = ShipmentStatus.Failed;
    this.failureReason = reason;
    this.save();
  }


  @AfterUpdate()
  async _hookafterUpdate(): Promise<void> {
    if (_fieldChanged(this, "status", this.__datrixOldValues!)) {
      const entity = this.__datrixEntityManager.getRepository(ShipmentEvent).create({shipment: this, timestamp: new Date(), status: this.status, location: 'System', description: `Status updated to ${this.status}`});
      await this.__datrixEntityManager.getRepository(ShipmentEvent).save(entity);
      if ((this.status === ShipmentStatus.InTransit)) {
        this.eventEmitter.emit('ShipmentDispatched', new ShipmentDispatchedEvent({ shipmentId: this.id, orderId: this.orderId, trackingNumber: this.trackingNumber }));
      } else if ((this.status === ShipmentStatus.Delivered)) {
        this.eventEmitter.emit('ShipmentDelivered', new ShipmentDeliveredEvent({ shipmentId: this.id, orderId: this.orderId, deliveredAt: (this.actualDelivery ?? new Date()) }));
      } else if ((this.status === ShipmentStatus.Failed)) {
        this.eventEmitter.emit('ShipmentFailed', new ShipmentFailedEvent({ shipmentId: this.id, orderId: this.orderId, reason: (this.failureReason ?? 'Delivery failed') }));
      }
    }
  }

}
