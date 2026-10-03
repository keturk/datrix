
import {
  IsDate,
  IsDefined,
  IsEnum,
  IsInt,
  IsOptional,
  IsUUID,
  ValidateIf,
} from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ReservationStatus } from '../enums/reservation-status.enum';

export class UpdateInventoryReservationDto {

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsUUID()
  reservationId?: string;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsInt()
  quantity?: number;

  @ApiPropertyOptional({ enum: ReservationStatus, enumName: 'ReservationStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(ReservationStatus)
  status?: ReservationStatus;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsDate()
  @Type(() => Date)
  expiresAt?: Date;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsUUID()
  productId?: string;
}
