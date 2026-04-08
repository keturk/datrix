# System Context Diagram (C4-inspired)

```mermaid
graph TD
    user_service("UserService")
    post_service("PostService")
    notification_service("NotificationService")
    post_service --> user_service
    notification_service --> user_service
```
