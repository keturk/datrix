# Data Store Topology

```mermaid
graph LR
    subgraph "AuthorService"
    author_service_rdbms_author_db[("authorDb / postgres (2 entities)")]
    author_service_mq_mq[["mq / MQ"]]
    end
    subgraph "ContentService"
    content_service_rdbms_content_db[("contentDb / postgres (1 entities)")]
    content_service_cache["redis"]
    content_service_mq_mq[["mq / MQ"]]
    end
    subgraph "CommentService"
    comment_service_rdbms_comment_db[("commentDb / postgres (1 entities)")]
    comment_service_mq_mq[["mq / MQ"]]
    end
```
