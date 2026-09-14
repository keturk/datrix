import {
  IsNotEmpty,
  IsString,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class VerifyEmailRequest {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  token!: string;


}
