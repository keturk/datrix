import {
  IsEmail,
  IsNotEmpty,
  IsString,
} from 'class-validator';

export class RegisterRequest {

  @IsEmail()
  email!: string;

  @IsString()
  @IsNotEmpty()
  password!: string;

  @IsString()
  @IsNotEmpty()
  firstName!: string;

  @IsString()
  @IsNotEmpty()
  lastName!: string;


}
