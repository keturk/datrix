import {
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ReleaseReservationRequest {

  @ApiProperty()
  @IsUUID()
  reservationId!: string;


}
