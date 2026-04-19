import {
  IsBoolean,
  IsOptional,
  IsString,
} from 'class-validator';

export class ChargeResult {

  @IsBoolean()
  success!: boolean;

  @IsOptional()
  @IsString()
  transactionId?: string | null;

  @IsOptional()
  @IsString()
  response?: string | null;

  @IsOptional()
  @IsString()
  error?: string | null;


}
