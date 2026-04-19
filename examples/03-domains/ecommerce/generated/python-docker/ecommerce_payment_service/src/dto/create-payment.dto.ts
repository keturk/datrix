
import {
  IsDate,
  IsEnum,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { Type } from 'class-transformer';
import { PaymentMethod } from '../enums/payment-method.enum';
import { PaymentStatus } from '../enums/payment-status.enum';

export class CreatePaymentDto {

  @IsUUID()
  orderId!: string;

  @IsUUID()
  customerId!: string;

  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @IsEnum(PaymentMethod)
  method!: PaymentMethod;

  @IsEnum(PaymentStatus)
  status!: PaymentStatus;

  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  transactionId!: string;

  @IsOptional()
  @IsString()
  gatewayResponse?: string | null;

  @IsOptional()
  @IsString()
  errorMessage?: string | null;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  processedAt?: Date | null;
}
