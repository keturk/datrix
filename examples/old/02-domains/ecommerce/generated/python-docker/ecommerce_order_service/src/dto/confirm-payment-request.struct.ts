import {
  IsUUID,
} from 'class-validator';

export class ConfirmPaymentRequest {

  @IsUUID()
  paymentId!: string;


}
