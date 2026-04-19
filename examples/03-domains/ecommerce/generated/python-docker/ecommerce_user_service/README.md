# ecommerce.UserService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8000)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| User | id, createdAt, updatedAt, email, passwordHash, firstName, lastName, phoneNumber, role, status, lastLoginAt, emailVerifiedAt, emailVerificationToken, passwordResetToken, passwordResetExpiry, shippingAddress, billingAddress | id |
| UserSession | id, createdAt, updatedAt, token, deviceName, ipAddress, userAgent, expiresAt, lastActivityAt | id |
| UserPreferences | id, createdAt, updatedAt, language, timezone, emailNotifications, smsNotifications, preferences | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/users | list_users |
| GET | /api/v1/users/:id | get_user |
| POST | /api/v1/users | create_user |
| PUT | /api/v1/users/:id | update_user |
| DELETE | /api/v1/users/:id | delete_user |
| POST | /api/v1/register | post |
| POST | /api/v1/login | post |
| POST | /api/v1/logout | post |
| GET | /api/v1/me | get |
| PUT | /api/v1/me | put |
| PUT | /api/v1/me/password | put |
| POST | /api/v1/verify-email | post |
| POST | /api/v1/forgot-password | post |
| POST | /api/v1/reset-password | post |
| PUT | /api/v1/:id/status | put |
| GET | /api/v1/internal/:id | get |
| POST | /api/v1/internal/validate-session | post |

## Events

| Topic | Events |
|-------|--------|
| UserEvents | UserRegistered, UserVerified, UserStatusChanged, UserLoggedIn |

## Cache

This service uses a cache block. See `.env.example` for `REDIS_URL`.

## Environment variables

See `.env.example` for required environment variables.

