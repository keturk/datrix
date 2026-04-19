import { ReservationStatus } from '../enums/reservation-status.enum';

export class InventoryReservationResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  reservationId!: string;
  quantity!: number;
  status!: ReservationStatus;
  expiresAt!: Date;
  productId!: string;

}
