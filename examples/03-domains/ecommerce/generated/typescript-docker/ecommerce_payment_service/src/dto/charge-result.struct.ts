import {
  IsBoolean,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class ChargeResult {

  @ApiProperty()
  @IsBoolean()
  success!: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  transactionId!: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  response!: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  error!: string | null;


}
