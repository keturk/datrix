import {
  IsNotEmpty,
  IsNumber,
  IsString,
} from 'class-validator';

export class RefundPaymentRequest {

  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @IsString()
  @IsNotEmpty()
  reason!: string;


}
