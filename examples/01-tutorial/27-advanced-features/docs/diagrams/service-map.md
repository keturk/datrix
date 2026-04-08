# Service Map with Infrastructure

```mermaid
graph LR
    book_service("BookService")
    member_service("MemberService")
    loan_service("LoanService")
    rdbms_1[("postgres (localhost:5432)")]
    book_service -->|library_books| rdbms_1
    member_service -->|library_members| rdbms_1
    loan_service -->|library_loans| rdbms_1
    cache_2["redis (localhost:6379)"]
    book_service --> cache_2
    mq_3[["kafka (localhost:9092)"]]
    book_service -->|mq| mq_3
    nosql_4[("mongodb")]
    book_service -->|library_analytics| nosql_4
    storage_5[/"Storage: store"/]
    book_service --> storage_5
    loan_service -->|HTTP| book_service
    loan_service -->|HTTP| member_service
```
