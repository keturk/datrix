import {
  IsArray,
  IsDate,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class IssueApiKeyRequest {

  @ApiProperty()
  @IsArray()
  @IsString({ each: true })
  scopes!: string[];

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  expiresAt!: Date | null;


}
