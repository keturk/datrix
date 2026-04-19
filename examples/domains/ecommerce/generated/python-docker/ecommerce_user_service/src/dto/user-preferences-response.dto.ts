
export class UserPreferencesResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  language!: string;
  timezone!: string;
  emailNotifications!: boolean;
  smsNotifications!: boolean;
  preferences!: Record<string, unknown>;
  userId!: string;

}
