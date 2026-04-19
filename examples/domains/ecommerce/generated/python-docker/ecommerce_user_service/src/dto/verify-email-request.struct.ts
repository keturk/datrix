import {
  IsNotEmpty,
  IsString,
} from 'class-validator';

export class VerifyEmailRequest {

  @IsString()
  @IsNotEmpty()
  token!: string;


}
