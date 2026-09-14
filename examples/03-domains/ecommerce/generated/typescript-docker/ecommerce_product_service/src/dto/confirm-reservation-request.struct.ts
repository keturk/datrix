import {
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ConfirmReservationRequest {

  @ApiProperty()
  @IsUUID()
  reservationId!: string;


}
