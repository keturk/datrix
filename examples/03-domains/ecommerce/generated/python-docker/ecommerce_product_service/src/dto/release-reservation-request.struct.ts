import {
  IsUUID,
} from 'class-validator';

export class ReleaseReservationRequest {

  @IsUUID()
  reservationId!: string;


}
