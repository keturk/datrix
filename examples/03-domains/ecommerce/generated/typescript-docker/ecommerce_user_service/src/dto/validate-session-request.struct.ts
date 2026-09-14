import {
  IsNotEmpty,
  IsString,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ValidateSessionRequest {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  token!: string;


}
