import {
  IsEnum,
  IsNumber,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { PaymentMethod } from '../enums/payment-method.enum'

export class ProcessPaymentRequest {

  @ApiProperty()
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @ApiProperty({ enum: PaymentMethod, enumName: 'PaymentMethod' })
  @IsEnum(PaymentMethod)
  method!: PaymentMethod;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  cardToken!: string | null;


}
