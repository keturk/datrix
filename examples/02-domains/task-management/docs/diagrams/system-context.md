# System Context Diagram (C4-inspired)

```mermaid
graph TD
    user_service("UserService")
    project_service("ProjectService")
    task_service("TaskService")
    project_service --> user_service
    task_service --> project_service
    task_service --> user_service
```
