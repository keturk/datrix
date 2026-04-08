# Entity Inheritance Tree

```mermaid
graph TD
    category["Category"]
    base_entity["BaseEntity (abstract)"]
    base_entity --> category
    user["User"]
    base_entity --> user
    tag["Tag"]
    base_entity --> tag
    book_tag["BookTag"]
    base_entity --> book_tag
    branch["Branch"]
    base_entity --> branch
    shelf_location["ShelfLocation"]
    base_entity --> shelf_location
    book["Book"]
    base_entity --> book
    trait_auditable{{"with Auditable"}}
    book -.-|trait| trait_auditable
    trait_soft_deletable{{"with SoftDeletable"}}
    book -.-|trait| trait_soft_deletable
    review["Review"]
    base_entity --> review
    checkout["Checkout"]
    base_entity --> checkout
    checkout -.-|trait| trait_auditable
    base_report_entity["BaseReportEntity (abstract)"]
    book_audit_log["BookAuditLog"]
    base_report_entity["BaseReportEntity (abstract)"]
    base_report_entity --> book_audit_log
    daily_book_stats["DailyBookStats"]
    base_report_entity --> daily_book_stats
    member["Member"]
    base_entity --> member
    member_preferences["MemberPreferences"]
    base_entity --> member_preferences
    loan["Loan"]
    base_entity --> loan
    idempotency_key["IdempotencyKey"]
    base_entity --> idempotency_key
```
