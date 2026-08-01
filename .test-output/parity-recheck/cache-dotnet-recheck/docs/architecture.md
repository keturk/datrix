# Architecture

## Overview

library is a microservice-based application built with ASP.NET Core and .NET 10.

## System Overview

| Property | Value |
|----------|-------|
| Services | 3 |
| Entities | 8 |
| Database | PostgreSQL (EF Core 10) |
| Framework | ASP.NET Core |
| Language | C# / .NET 10 |
| Architecture | Clean Architecture |
| Deployment | docker-compose |

## Architecture Diagram

```mermaid
graph TD
    clientNode[Client]
    clientNode --> gatewayNode[API_Gateway]
    gatewayNode --> book["BookService"]
    gatewayNode --> member["MemberService"]
    gatewayNode --> loan["LoanService"]
    book --> book_db[("BookService_DB")]
    book --> book_cache["Redis_Cache"]
    member --> member_db[("MemberService_DB")]
    loan --> loan_db[("LoanService_DB")]
    loan --> library_book_service
    loan --> library_member_service
```

## Services

### BookService

- **Port:** 8000
- **Directory:** `library_book_service/`
- **Entities:** BaseEntity, Book, Category, User
- **REST API:** Yes

### MemberService

- **Port:** 8002
- **Directory:** `library_member_service/`
- **Entities:** BaseEntity, Member
- **REST API:** Yes

### LoanService

- **Port:** 8001
- **Directory:** `library_loan_service/`
- **Entities:** BaseEntity, Loan
- **REST API:** Yes



## Database Schema

### Entity Relationships

```mermaid
erDiagram
    BaseEntity {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
    }

    Category {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
        String(100) name
        String(500)? description
    }

    User {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
        String(255) email
        Password passwordHash
        UserRole role
    }

    Book {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
        String(200) title
        String(10, 13) isbn
        String(100) author
        Integer publicationYear
        BookStatus status
        BookFormat format
        String(50)? catalogNumber
        Array<String> keywords
        Decimal(3, 2) rating
        UUID categoryId
    }

    BaseEntity {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
    }

    Member {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
        String(100) firstName
        String(100) lastName
        Email email
        String(20) membershipNumber
        MembershipType membershipType
    }

    BaseEntity {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
    }

    Loan {

        UUID id PK
        DateTime createdAt
        DateTime updatedAt
        UUID bookId
        UUID memberId
        LoanStatus status
        DateTime dueDate
        DateTime? returnedAt
    }

    Category ||--o{ Book : "books"

    Book }o--|| Category : "belongsTo"

```

### Entity Details

#### BaseEntity

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |

#### Category

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |
| `name` | String(100) | No | Name |
| `description` | String(500)? | Yes | Description |

#### User

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |
| `email` | String(255) | No | Email |
| `passwordHash` | Password | No | Passwordhash |
| `role` | UserRole | No | Role |

#### Book

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |
| `title` | String(200) | No | Title |
| `isbn` | String(10, 13) | No | Isbn |
| `author` | String(100) | No | Author |
| `publicationYear` | Integer | No | Publicationyear |
| `status` | BookStatus | No | Status |
| `format` | BookFormat | No | Format |
| `catalogNumber` | String(50)? | Yes | Catalognumber |
| `keywords` | Array<String> | No | Keywords |
| `rating` | Decimal(3, 2) | No | Rating |
| `categoryId` | UUID | No | Categoryid |

#### BaseEntity

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |

#### Member

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |
| `firstName` | String(100) | No | Firstname |
| `lastName` | String(100) | No | Lastname |
| `email` | Email | No | Email |
| `membershipNumber` | String(20) | No | Membershipnumber |
| `membershipType` | MembershipType | No | Membershiptype |

#### BaseEntity

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |

#### Loan

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | UUID | No | Id |
| `createdAt` | DateTime | No | Createdat |
| `updatedAt` | DateTime | No | Updatedat |
| `bookId` | UUID | No | Bookid |
| `memberId` | UUID | No | Memberid |
| `status` | LoanStatus | No | Status |
| `dueDate` | DateTime | No | Duedate |
| `returnedAt` | DateTime? | Yes | Returnedat |


## Infrastructure Components

| Component | Description |
|-----------|-------------|
| ASP.NET Core | Kestrel-hosted web framework with `Microsoft.AspNetCore.OpenApi` document generation |
| EF Core 10 | Object-relational mapper for PostgreSQL access |
| Structured Logging | JSON logging in production, console logging in development |
| Health Checks | `/health` (dependency-gated) and `/live` (dependency-free) endpoints |
| Middleware | CORS, request logging, error handling |
| Prometheus Metrics | `/metrics` endpoint for scraping |
| OpenTelemetry | Distributed tracing with OTLP export |
| Redis Cache | Caching layer for performance optimization |
| Message Queue | Async event-driven communication |

## Service Dependencies

```mermaid
graph LR
    loan["LoanService"] --> library_book_service["BookService"]
    loan["LoanService"] --> library_member_service["MemberService"]
```

- **LoanService** -> **BookService**: HTTP client communication
- **LoanService** -> **MemberService**: HTTP client communication

---

*Generated by datrix-codegen-dotnet*
