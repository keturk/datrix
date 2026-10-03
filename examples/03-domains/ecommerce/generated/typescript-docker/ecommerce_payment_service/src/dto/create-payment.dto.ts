
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
import { PaymentMethod } from '../enums/payment-method.enum';
import { PaymentStatus } from '../enums/payment-status.enum';

export class CreatePaymentDto {

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  customerId!: string;

  @ApiProperty()
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @ApiProperty({ enum: PaymentMethod, enumName: 'PaymentMethod' })
  @IsDefined()
  @IsEnum(PaymentMethod)
  method!: PaymentMethod;

  @ApiPropertyOptional({ enum: PaymentStatus, enumName: 'PaymentStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(PaymentStatus)
  status?: PaymentStatus;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  transactionId!: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  gatewayResponse?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  errorMessage?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  processedAt?: Date | null;
}
