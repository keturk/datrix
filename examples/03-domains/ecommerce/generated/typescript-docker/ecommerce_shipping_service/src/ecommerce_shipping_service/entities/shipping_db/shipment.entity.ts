import {
  Entity,
  Property,
  Enum,
  OneToMany,
  Collection,
  Index,
  OptionalProps,
  wrap,
} from '@mikro-orm/core';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { Address } from '../../../dto/address.struct'
import { _fieldChanged, _fieldOldValue } from '../../../entity-hook-helpers';
import { differenceInDays } from 'date-fns';

import { ShipmentEvent } from './shipment-event.entity';
import { ShippingCarrier } from '../../../enums/shipping-carrier.enum';
import { ShipmentStatus } from '../../../enums/shipment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_shipments_order_id', properties: ['orderId'] })
@Index({ name: 'idx_shipments_tracking_number', properties: ['trackingNumber'] })
@Index({ name: 'idx_shipments_status', properties: ['status'] })
@Index({ name: 'idx_shipments_carrier_status', properties: ['carrier', 'status'] })
@Entity({ tableName: 'shipments' })
export class Shipment extends BaseEntity {
  [OptionalProps]?: "actualDelivery" | "createdAt" | "daysInTransit" | "estimatedDelivery" | "eventEmitter" | "failureReason" | "id" | "isDelivered" | "isInProgress" | "status" | "updatedAt";

  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('@mikro-orm/core').EntityManager;

  @Property({ columnType: 'uuid', fieldName: 'order_id' })
  orderId!: string;

  @Property({ columnType: 'varchar', fieldName: 'tracking_number', unique: true })
  trackingNumber!: string;

  @Enum({ items: () => ShippingCarrier, nativeEnumName: 'shipping_carrier' })
  carrier!: ShippingCarrier;

  @Enum({ items: () => ShipmentStatus, nativeEnumName: 'shipment_status' })
  status!: ShipmentStatus;

  @Property({ columnType: 'jsonb', type: 'json' })
  destination!: Address;

  @Property({ columnType: 'decimal' })
  weight!: number;

  @Property({ columnType: 'timestamptz', fieldName: 'estimated_delivery', nullable: true })
  estimatedDelivery!: Date | null;

  @Property({ columnType: 'timestamptz', fieldName: 'actual_delivery', nullable: true })
  actualDelivery!: Date | null;

  @Property({ columnType: 'varchar', fieldName: 'failure_reason', nullable: true })
  failureReason!: string | null;


  @OneToMany({ entity: () => ShipmentEvent, mappedBy: 'shipment' })
  events = new Collection<ShipmentEvent>(this);

  get isDelivered(): boolean {
    return (this.status === ShipmentStatus.Delivered);
  }
  get isInProgress(): boolean {
    return ((this.status === ShipmentStatus.InTransit) || (this.status === ShipmentStatus.OutForDelivery));
  }
  get daysInTransit(): number {
    return this.calculateDaysInTransit();
  }

  /** Persist pending entity changes via the associated EntityManager. */
  async save(): Promise<void> {
    await wrap(this, true).__em!.flush();
  }

  calculateDaysInTransit(): number {
    if ((this.actualDelivery == null)) {
      return 0;
    }
    return differenceInDays(this.actualDelivery, this.createdAt!);
  }

  async markDelivered(): Promise<void> {
    this.status = ShipmentStatus.Delivered;
    this.actualDelivery = new Date();
    await this.save();
  }

  async markFailed(reason: string): Promise<void> {
    this.status = ShipmentStatus.Failed;
    this.failureReason = reason;
    await this.save();
  }


}
