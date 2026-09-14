import {
  IsBoolean,
  IsInt,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class PaginationResult {

  @ApiProperty()
  @IsInt()
  page!: number;

  @ApiProperty()
  @IsInt()
  perPage!: number;

  @ApiProperty()
  @IsInt()
  total!: number;

  @ApiProperty()
  @IsInt()
  totalPages!: number;

  @ApiProperty()
  @IsBoolean()
  hasNext!: boolean;

  @ApiProperty()
  @IsBoolean()
  hasPrev!: boolean;


}
