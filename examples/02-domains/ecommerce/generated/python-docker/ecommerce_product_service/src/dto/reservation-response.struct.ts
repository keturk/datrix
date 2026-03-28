import {
  IsBoolean,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';

export class ReservationResponse {

  @IsBoolean()
  success!: boolean;

  @IsOptional()
  @IsUUID()
  reservationId?: string | null;

  @IsOptional()
  @IsString()
  error?: string | null;


}
