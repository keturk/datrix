import {
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ConfirmPaymentRequest {

  @ApiProperty()
  @IsUUID()
  paymentId!: string;


}
