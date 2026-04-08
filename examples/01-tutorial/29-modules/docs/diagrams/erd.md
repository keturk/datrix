# Entity-Relationship Diagram

```mermaid
erDiagram
    Category ||--o{ Book : "books"
    Tag ||--o{ BookTag : "bookTags"
    BookTag }o--|| Book : "belongsTo"
    BookTag }o--|| Tag : "belongsTo"
    Branch ||--o{ ShelfLocation : "shelves"
    ShelfLocation }o--|| Branch : "belongsTo"
    Book }o--|| Category : "belongsTo"
    Book }o--|| Branch : "belongsTo"
    Book ||--o{ BookTag : "bookTags"
    Book ||--o{ Review : "reviews"
    Review }o--|| Book : "belongsTo"
    Checkout }o--|| Book : "belongsTo"
```
