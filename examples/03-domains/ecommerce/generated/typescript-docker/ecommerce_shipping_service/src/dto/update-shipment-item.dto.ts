
import { PartialType } from '@nestjs/swagger';
import { CreateShipmentItemDto } from './create-shipment-item.dto';

export class UpdateShipmentItemDto extends PartialType(CreateShipmentItemDto) {}
