import {
  IsInt,
  IsNotEmpty,
  IsNumber,
  IsString,
  IsUUID,
} from 'class-validator';

export class CreateProductRequest {

  @IsString()
  @IsNotEmpty()
  name!: string;

  @IsString()
  @IsNotEmpty()
  description!: string;

  @IsNumber({ maxDecimalPlaces: 4 })
  price!: number;

  @IsUUID()
  categoryId!: string;

  @IsInt()
  inventory!: number;


}
