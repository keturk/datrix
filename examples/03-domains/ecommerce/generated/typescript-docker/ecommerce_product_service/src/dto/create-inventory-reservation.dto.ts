
import {
  IsDate,
  IsEnum,
  IsInt,
  IsOptional,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ReservationStatus } from '../enums/reservation-status.enum';

export class CreateInventoryReservationDto {

  @ApiProperty()
  @IsUUID()
  reservationId!: string;

  @ApiProperty()
  @IsInt()
  quantity!: number;

  @ApiProperty({ enum: ReservationStatus, enumName: 'ReservationStatus' })
  @IsEnum(ReservationStatus)
  status!: ReservationStatus;

  @ApiProperty()
  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;

  @ApiProperty()
  @IsUUID()
  productId!: string;
}
