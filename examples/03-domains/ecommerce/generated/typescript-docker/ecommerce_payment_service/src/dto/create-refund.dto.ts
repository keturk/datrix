
import {
  IsDate,
  IsDefined,
  IsEnum,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
  ValidateIf,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { PaymentStatus } from '../enums/payment-status.enum';

export class CreateRefundDto {

  @ApiProperty()
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(500)
  reason!: string;

  @ApiPropertyOptional({ enum: PaymentStatus, enumName: 'PaymentStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(PaymentStatus)
  status?: PaymentStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  refundTransactionId?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  errorMessage?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  processedAt?: Date | null;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  paymentId!: string;
}
