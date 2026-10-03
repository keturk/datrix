
import {
  IsDate,
  IsDefined,
  IsEnum,
  IsInt,
  IsOptional,
  IsUUID,
  ValidateIf,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ReservationStatus } from '../enums/reservation-status.enum';

export class CreateInventoryReservationDto {

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  reservationId!: string;

  @ApiProperty()
  @IsDefined()
  @IsInt()
  quantity!: number;

  @ApiPropertyOptional({ enum: ReservationStatus, enumName: 'ReservationStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(ReservationStatus)
  status?: ReservationStatus;

  @ApiProperty()
  @IsDefined()
  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  productId!: string;
}
