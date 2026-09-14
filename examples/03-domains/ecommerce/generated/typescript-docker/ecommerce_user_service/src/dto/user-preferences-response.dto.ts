
export class UserPreferencesResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  language!: string;
  timezone!: string;
  emailNotifications!: boolean;
  smsNotifications!: boolean;
  preferences!: Record<string, any>;
  userId!: string;

}
