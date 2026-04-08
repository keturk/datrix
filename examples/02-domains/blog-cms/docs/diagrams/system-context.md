# System Context Diagram (C4-inspired)

```mermaid
graph TD
    author_service("AuthorService")
    content_service("ContentService")
    comment_service("CommentService")
    content_service --> author_service
    comment_service --> content_service
```
