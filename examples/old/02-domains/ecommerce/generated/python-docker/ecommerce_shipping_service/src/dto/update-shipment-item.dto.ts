
import { PartialType } from '@nestjs/mapped-types';
import { CreateShipmentItemDto } from './create-shipment-item.dto';

export class UpdateShipmentItemDto extends PartialType(CreateShipmentItemDto) {}
