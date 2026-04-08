# Entity-Relationship Diagram

```mermaid
erDiagram
    Category ||--o{ Book : "books"
    Book }o--|| Category : "belongsTo"
```
