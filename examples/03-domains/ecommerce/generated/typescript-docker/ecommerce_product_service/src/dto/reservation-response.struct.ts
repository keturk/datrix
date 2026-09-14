import {
  IsBoolean,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class ReservationResponse {

  @ApiProperty()
  @IsBoolean()
  success!: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @IsUUID()
  reservationId!: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  error!: string | null;


}
