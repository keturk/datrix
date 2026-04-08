# Entity-Relationship Diagram

```mermaid
erDiagram
    AuthorSession }o--|| Author : "belongsTo"
    Comment }o--|| Comment : "parent"
    Comment ||--o{ Comment : "replies"
```
