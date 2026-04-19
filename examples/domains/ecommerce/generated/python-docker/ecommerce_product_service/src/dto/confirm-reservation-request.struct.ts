import {
  IsUUID,
} from 'class-validator';

export class ConfirmReservationRequest {

  @IsUUID()
  reservationId!: string;


}
