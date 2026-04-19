
import { PartialType } from '@nestjs/mapped-types';
import { CreateInventoryReservationDto } from './create-inventory-reservation.dto';

export class UpdateInventoryReservationDto extends PartialType(CreateInventoryReservationDto) {}
