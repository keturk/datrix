
import {
  IsDate,
  IsNotEmpty,
  IsOptional,
  IsString,
  IsUUID,
  Matches,
  Max,
  MaxLength,
} from 'class-validator';
import { Type } from 'class-transformer';

export class CreateCategoryDto {

  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  name!: string;

  @IsOptional()
  @IsString()
  description?: string | null;

  @Matches(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
  slug!: string;
}
