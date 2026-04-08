# Data Store Topology

```mermaid
graph LR
    subgraph "BookService"
    book_service_rdbms_db[("db / postgres (4 entities)")]
    book_service_mq_mq[["mq / MQ"]]
    end
    subgraph "MemberService"
    member_service_rdbms_db[("db / postgres (2 entities)")]
    end
```
