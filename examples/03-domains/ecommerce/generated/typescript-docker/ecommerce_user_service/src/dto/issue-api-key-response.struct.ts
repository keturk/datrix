import {
  IsNotEmpty,
  IsString,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class IssueApiKeyResponse {

  @ApiProperty()
  @IsUUID()
  id!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  apiKey!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  keyPrefix!: string;


}
