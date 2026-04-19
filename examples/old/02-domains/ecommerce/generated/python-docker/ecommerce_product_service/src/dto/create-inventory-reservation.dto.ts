
import {
  IsDate,
  IsEnum,
  IsInt,
  IsOptional,
  IsUUID,
} from 'class-validator';
import { Type } from 'class-transformer';
import { ReservationStatus } from '../enums/reservation-status.enum';

export class CreateInventoryReservationDto {

  @IsUUID()
  reservationId!: string;

  @IsInt()
  quantity!: number;

  @IsEnum(ReservationStatus)
  status!: ReservationStatus;

  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;

  @IsUUID()
  productId!: string;
}
