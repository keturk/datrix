import {
  IsNotEmpty,
  IsString,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ApiKeyVerifyRequest {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  keyHash!: string;


}
