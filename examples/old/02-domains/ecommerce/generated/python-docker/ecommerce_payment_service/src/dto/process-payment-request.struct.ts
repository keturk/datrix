import {
  IsEnum,
  IsNumber,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { PaymentMethod } from '../enums/payment-method.enum'

export class ProcessPaymentRequest {

  @IsUUID()
  orderId!: string;

  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @IsEnum(PaymentMethod)
  method!: PaymentMethod;

  @IsOptional()
  @IsString()
  cardToken?: string | null;


}
