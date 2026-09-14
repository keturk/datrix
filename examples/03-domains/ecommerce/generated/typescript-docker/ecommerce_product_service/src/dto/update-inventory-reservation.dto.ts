
import { PartialType } from '@nestjs/swagger';
import { CreateInventoryReservationDto } from './create-inventory-reservation.dto';

export class UpdateInventoryReservationDto extends PartialType(CreateInventoryReservationDto) {}
