import {
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';

export class CancelOrderRequest {

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  reason!: string | null;


}
