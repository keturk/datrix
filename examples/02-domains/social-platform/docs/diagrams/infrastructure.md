# Data Store Topology

```mermaid
graph LR
    subgraph "UserService"
    user_service_rdbms_user_db[("userDb / postgres (1 entities)")]
    end
    subgraph "PostService"
    post_service_rdbms_post_db[("postDb / postgres (1 entities)")]
    end
    subgraph "NotificationService"
    notification_service_rdbms_notification_db[("notificationDb / postgres (1 entities)")]
    end
```
