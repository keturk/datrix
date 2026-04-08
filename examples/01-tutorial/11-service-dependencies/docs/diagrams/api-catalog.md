# API Catalog (Markdown table)

| Service | Method | Path | Entity |
|---------|--------|------|--------|
| BookService | GET | /api/v1/books | Ref('Book', UNRESOLVED) |
| BookService | GET | /api/v1/books/:id | Ref('Book', UNRESOLVED) |
| BookService | POST | /api/v1/books | Ref('Book', UNRESOLVED) |
| BookService | PUT | /api/v1/books/:id | Ref('Book', UNRESOLVED) |
| BookService | DELETE | /api/v1/books/:id | Ref('Book', UNRESOLVED) |
| BookService | GET | /api/v1/categories | Ref('Category', UNRESOLVED) |
| BookService | GET | /api/v1/categories/:id | Ref('Category', UNRESOLVED) |
| BookService | POST | /api/v1/categories | Ref('Category', UNRESOLVED) |
| BookService | PUT | /api/v1/categories/:id | Ref('Category', UNRESOLVED) |
| BookService | DELETE | /api/v1/categories/:id | Ref('Category', UNRESOLVED) |
| BookService | GET | /api/v1/books/search |  |
| BookService | GET | /api/v1/books/category/:categoryId |  |
| MemberService | GET | /api/v1/members/members | Ref('Member', UNRESOLVED) |
| MemberService | GET | /api/v1/members/members/:id | Ref('Member', UNRESOLVED) |
| MemberService | POST | /api/v1/members/members | Ref('Member', UNRESOLVED) |
| MemberService | PUT | /api/v1/members/members/:id | Ref('Member', UNRESOLVED) |
| MemberService | DELETE | /api/v1/members/members/:id | Ref('Member', UNRESOLVED) |
| MemberService | GET | /api/v1/members/by-membership/:membershipNumber |  |
| LoanService | POST | /api/v1/loans |  |
| LoanService | GET | /api/v1/loans/member/:memberId |  |
