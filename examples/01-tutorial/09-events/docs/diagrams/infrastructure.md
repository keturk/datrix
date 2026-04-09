# Data Store Topology

```mermaid
graph LR
    subgraph "BookService"
    book_service_rdbms_book_db[("bookDb / postgres (4 entities)")]
    book_service_mq_mq[["mq / MQ"]]
    end
```
