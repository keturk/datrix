import { Injectable, NotFoundException, Logger, ConflictException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ShipmentDeliveredEvent } from '../events/shipment-delivered.event';
import { ShipmentDispatchedEvent } from '../events/shipment-dispatched.event';
import { ShipmentFailedEvent } from '../events/shipment-failed.event';
import { ShipmentStatus } from '../enums/shipment-status.enum'
import { ShippingCarrier } from '../enums/shipping-carrier.enum'
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { Shipment } from '../entities/shipment.entity';
import { CreateShipmentDto } from '../dto/create-shipment.dto';
import { UpdateShipmentDto } from '../dto/update-shipment.dto';
import { ShipmentEvent } from '../entities/shipment-event.entity';

@Injectable()
export class ShipmentService {
  private readonly logger = new Logger(ShipmentService.name);

  constructor(
    @InjectRepository(Shipment)
    private readonly shipmentRepository: Repository<Shipment>,
    @InjectRepository(ShipmentEvent)
    private readonly shipmentEventRepository: Repository<ShipmentEvent>,
    private readonly dataSource: DataSource,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(): Promise<Shipment[]> {
    this.logger.log('Finding all Shipment');
    return this.shipmentRepository.find();
  }

  async findOne(id: string): Promise<Shipment> {
    const entity = await this.shipmentRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`Shipment with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateShipmentDto): Promise<Shipment> {
    const entity = this.shipmentRepository.create(dto);
    const saved = await this.shipmentRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateShipmentDto): Promise<Shipment> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    Object.assign(entity, dto);
    const updated = await this.shipmentRepository.save(entity);
if (this._fieldChanged(updated, "status", oldValues)) {
  const entity = this.shipmentEventRepository.create({shipment: updated, timestamp: new Date(), status: updated.status, location: 'System', description: `Status updated to ${updated.status}`});
  await this.shipmentEventRepository.save(entity);
  if ((updated.status === ShipmentStatus.InTransit)) {
    this.eventEmitter.emit('ShipmentDispatched', new ShipmentDispatchedEvent({ shipmentId: updated.id, orderId: updated.orderId, trackingNumber: updated.trackingNumber }));
  } else if ((updated.status === ShipmentStatus.Delivered)) {
    this.eventEmitter.emit('ShipmentDelivered', new ShipmentDeliveredEvent({ shipmentId: updated.id, orderId: updated.orderId, deliveredAt: (updated.actualDelivery ?? new Date()) }));
  } else if ((updated.status === ShipmentStatus.Failed)) {
    this.eventEmitter.emit('ShipmentFailed', new ShipmentFailedEvent({ shipmentId: updated.id, orderId: updated.orderId, reason: (updated.failureReason ?? 'Delivery failed') }));
  }
}
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const shipmentEventCount = await this.dataSource
      .getRepository(ShipmentEvent)
      .count({ where: { shipmentId: id } as any });
    if (shipmentEventCount > 0) {
      throw new ConflictException(
        `Cannot delete Shipment '${id}': ` +
        `${ shipmentEventCount } events still reference it. ` +
        `Delete or reassign ShipmentEvent records first.`,
      );
    }
    await this.shipmentRepository.remove(entity);
  }

  private _fieldChanged(
    current: Shipment,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): boolean {
    if (snapshot === undefined) {
      return false;
    }
    const cur = current as unknown as Record<string, unknown>;
    return snapshot[fieldName] !== cur[fieldName];
  }

  private _fieldOldValue(
    current: Shipment,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): unknown {
    if (snapshot === undefined) {
      return undefined;
    }
    return snapshot[fieldName];
  }



  async findByOrderId(orderId: string, skip = 0, take = 100): Promise<Shipment[]> {
    return this.shipmentRepository.find({ where: { orderId } as any, skip, take });
  }
  async getByTrackingNumber(trackingNumber: string): Promise<Shipment> {
    const entity = await this.shipmentRepository.findOne({ where: { trackingNumber } as any });
    if (!entity) {
      throw new NotFoundException(`Shipment with trackingNumber ${ trackingNumber } not found`);
    }
    return entity;
  }
  async findByCarrierAndStatus(carrier: ShippingCarrier, status: ShipmentStatus, skip = 0, take = 100): Promise<Shipment[]> {
    return this.shipmentRepository.find({
      where: { carrier, status } as any,
      skip,
      take,
    });
  }

}
