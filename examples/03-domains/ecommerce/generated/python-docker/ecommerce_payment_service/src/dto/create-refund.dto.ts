
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
import { PaymentStatus } from '../enums/payment-status.enum';

export class CreateRefundDto {

  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @IsString()
  @IsNotEmpty()
  @MaxLength(500)
  reason!: string;

  @IsEnum(PaymentStatus)
  status!: PaymentStatus;

  @IsOptional()
  @IsString()
  refundTransactionId?: string | null;

  @IsOptional()
  @IsString()
  errorMessage?: string | null;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  processedAt?: Date | null;

  @IsUUID()
  paymentId!: string;
}
