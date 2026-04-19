
import { PartialType } from '@nestjs/mapped-types';
import { CreateShipmentEventDto } from './create-shipment-event.dto';

export class UpdateShipmentEventDto extends PartialType(CreateShipmentEventDto) {}
