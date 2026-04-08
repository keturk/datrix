# Data Store Topology

```mermaid
graph LR
    subgraph "BookService"
    book_service_rdbms_db[("db / postgres (6 entities)")]
    book_service_cache["redis"]
    book_service_mq_mq[["mq / MQ"]]
    end
    subgraph "MemberService"
    member_service_rdbms_db[("db / postgres (2 entities)")]
    end
    subgraph "LoanService"
    loan_service_rdbms_db[("db / postgres (2 entities)")]
    end
```
