import {
  IsBoolean,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class RefundResult {

  @ApiProperty()
  @IsBoolean()
  success!: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  refundTransactionId!: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  error!: string | null;


}
