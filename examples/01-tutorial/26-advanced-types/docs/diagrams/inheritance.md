# Entity Inheritance Tree

```mermaid
graph TD
    base_entity["BaseEntity (abstract)"]
    category["Category"]
    base_entity["BaseEntity (abstract)"]
    base_entity --> category
    user["User"]
    base_entity --> user
    tag["Tag"]
    base_entity --> tag
    book_tag["BookTag"]
    base_entity --> book_tag
    branch["Branch"]
    base_entity --> branch
    shelf_location["ShelfLocation"]
    base_entity --> shelf_location
    book["Book"]
    base_entity --> book
    review["Review"]
    base_entity --> review
    member["Member"]
    base_entity --> member
    loan["Loan"]
    base_entity --> loan
```
