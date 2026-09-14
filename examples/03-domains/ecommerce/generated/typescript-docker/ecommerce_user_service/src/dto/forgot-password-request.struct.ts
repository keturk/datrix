import {
  IsEmail,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ForgotPasswordRequest {

  @ApiProperty()
  @IsEmail()
  email!: string;


}
