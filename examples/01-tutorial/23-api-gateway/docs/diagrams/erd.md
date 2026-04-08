# Entity-Relationship Diagram

```mermaid
erDiagram
    Category ||--o{ Book : "books"
    Tag ||--o{ BookTag : "bookTags"
    BookTag }o--|| Book : "belongsTo"
    BookTag }o--|| Tag : "belongsTo"
    Book }o--|| Category : "belongsTo"
    Book ||--o{ BookTag : "bookTags"
```
