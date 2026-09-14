import { ReservationStatus } from '../enums/reservation-status.enum';

export class InventoryReservationResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  reservationId!: string;
  quantity!: number;
  status!: ReservationStatus;
  expiresAt!: Date;
  productId!: string;

}
