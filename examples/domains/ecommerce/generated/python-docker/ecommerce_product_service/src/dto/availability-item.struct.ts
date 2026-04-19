import {
  IsBoolean,
  IsInt,
  IsUUID,
} from 'class-validator';

export class AvailabilityItem {

  @IsUUID()
  productId!: string;

  @IsBoolean()
  available!: boolean;

  @IsInt()
  availableQuantity!: number;


}
