# System Context Diagram (C4-inspired)

```mermaid
graph TD
    book_service("BookService")
    member_service("MemberService")
    loan_service("LoanService")
    loan_service --> book_service
    loan_service --> member_service
```
