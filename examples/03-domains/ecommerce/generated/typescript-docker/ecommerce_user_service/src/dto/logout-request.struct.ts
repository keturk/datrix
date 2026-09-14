import {
  IsBoolean,
  IsOptional,
} from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';

export class LogoutRequest {

  @ApiPropertyOptional()
  @IsOptional()
  @IsBoolean()
  revokeAll!: boolean | null;


}
