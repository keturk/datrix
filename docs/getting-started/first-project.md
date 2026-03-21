# Your First Project

**Last Updated:** March 16, 2026

A complete walkthrough for creating your first Datrix project from scratch.

---

## Overview

In this tutorial, you'll create a blog service with:
- User entity (authors)
- Post entity (blog posts)
- BlogService with REST API
- Generated FastAPI application

**Time:** 15-20 minutes

---

## Step 1: Project Setup

### Create Project Directory

```bash
mkdir blog-service
cd blog-service
mkdir specs
```

---

## Step 2: Create .dtrx Specification

Create `specs/blog-service.dtrx` (service with entities and API):

```datrix
// blog-service.dtrx - Blog Service Specification

service blog.BlogService : version('1.0.0') {

 registration('config/blog-service/registration.yaml');
 discovery { }
 resilience('config/blog-service/resilience.yaml');

 rdbms db('config/blog-service/datasources.yaml') {

 abstract entity BaseEntity {
 @UUID id : primaryKey = uuid();
 @UDateTime createdAt = utcNow();
 @UDateTime updatedAt = utcNow();
 }

 entity User extends BaseEntity {
 String(100) name;
 Email email;
 }

 entity Post extends BaseEntity {
 String(200) title;
 String content;
 belongsTo User as author : index;
 }
 }

 rest_api BlogAPI : basePath("/api/v1") {
 resource db.User;
 resource db.Post;
 }
}
```

Then create `specs/system.dtrx` (entry point):

```datrix
// system.dtrx
include 'blog-service.dtrx';

system blog.System : version('1.0.0') {
 registry('config/registry.yaml');
 gateway('config/gateway.yaml');
 observability('config/observability.yaml');
 config('config/system-config.yaml');
}
```

**Save both files in `specs/`.** See [examples/01-tutorial/01-basic-entity](../../examples/01-tutorial/01-basic-entity/) and [examples/01-tutorial/05-relationships](../../examples/01-tutorial/05-relationships/) for more examples.

### Field attributes

You can attach attributes to fields to control validation and behavior:

- **`trim`** — Trim leading/trailing whitespace on string input.
- **`unique`** — Enforce uniqueness (database unique constraint).
- **`index`** — Create an index on the column (or FK) for faster lookups.
- **`hidden`** — Exclude from API responses.
- **`immutable`** — Include in Create, exclude from Update.

Example: `String(100) name : unique, trim;` or `belongsTo User as author : index;`. See the [Language Reference](../reference/language-reference.md) for more details.

---

## Step 3: Install Required Generators

```bash
# Install Python generator for FastAPI
pip install datrix-codegen-python

# Optional: Install SQL generator for database migrations
pip install datrix-codegen-sql
```

---

## Step 4: Validate Specification

```bash
datrix validate specs/system.dtrx
```

**Expected output:**
```
✓ Validation successful
✓ Found 1 service: BlogService
✓ Found 2 entities: User, Post
✓ Found 1 relationship: Post.author -> User
```

If you see errors, check your `.dtrx` file syntax.

---

## Step 5: Generate Code

### Generate Python/FastAPI Application

```bash
datrix generate --source specs/system.dtrx --output ./generated
```

**Expected output:**
```
Generating code...
✓ Parsed specs/system.dtrx
✓ Built application model
✓ Generated Python/FastAPI code
✓ Generated files in generated/blog-service/
```

Each service gets its own subdirectory (e.g. `blog-service` for `blog.BlogService`). The `app/` folder contains `main.py`, `models/`, `routes/`, and `schemas/`.

### SQL Migrations

SQL DDL is generated automatically alongside Python code when `language: python` is set in `system-config.yaml`. The SQL generator runs as part of the standard generation pipeline.

---

## Step 6: Review Generated Code

### Generated File Structure

```
generated/
└── blog-service/
 ├── app/
 │ ├── main.py # FastAPI application entry point
 │ ├── models/
 │ │ ├── __init__.py
 │ │ ├── user.py # Pydantic User model
 │ │ └── post.py # Pydantic Post model
 │ ├── routes/
 │ │ ├── __init__.py
 │ │ ├── user_routes.py # FastAPI routes for User
 │ │ └── post_routes.py # FastAPI routes for Post
 │ └── schemas/
 │ ├── __init__.py
 │ ├── user_schemas.py # API request/response schemas
 │ └── post_schemas.py # API request/response schemas
 └── requirements.txt # Python dependencies
```

### Example Generated Model

**`generated/blog-service/app/models/user.py`:**
```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class User(BaseModel):
 """User model generated from User entity."""
 
 id: UUID
 name: str
 email: str
 created_at: datetime
```

### Example Generated Route

**`generated/blog-service/app/routes/user_routes.py`:**
```python
from fastapi import APIRouter, HTTPException
from models.user import User
from schemas.user_schemas import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserResponse)
async def create_user(data: UserCreate) -> UserResponse:
 """Create a new user."""
 # Implementation here
 ...

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID) -> UserResponse:
 """Get user by ID."""
 # Implementation here
 ...
```

---

## Step 7: Run Generated Application

### Install Dependencies

```bash
cd generated/blog-service
pip install -r requirements.txt
```

### Start the Server

```bash
python -m app.main
```

**Expected output:**
```
INFO: Started server process [12345]
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### Access API Documentation

Open your browser and visit:
- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

---

## Step 8: Test the API

### Create a User

```bash
curl -X POST "http://127.0.0.1:8000/users/" \
 -H "Content-Type: application/json" \
 -d '{
 "name": "John Doe",
 "email": "john@example.com"
 }'
```

### Get All Users

```bash
curl "http://127.0.0.1:8000/users/"
```

### Create a Post

```bash
curl -X POST "http://127.0.0.1:8000/posts/" \
 -H "Content-Type: application/json" \
 -d '{
 "title": "My First Post",
 "content": "This is my first blog post!",
 "authorId": "<user-id-from-previous-response>"
 }'
```

---

## Step 9: Extend Your Specification

Datrix generates complete, production-ready code. To add features, update your `.dtrx` specification:

1. **Add computed fields** for derived values
2. **Add validators** for field validation rules
3. **Add relationships** between entities
4. **Configure authentication** in your service definition
5. **Add custom methods** to services

All business logic, database integration, and validation is generated from your specification.

---

## Step 10: Regenerate Code

When you update your `.dtrx` file, regenerate code:

```bash
# Update specs/system.dtrx
# ... make changes ...

# Regenerate
datrix generate --source specs/system.dtrx --output ./generated
```

Generated files are fully managed by Datrix - modify your `.dtrx` specification to change the output.

---

## Next Steps

### Add More Features

1. **Add Comment entity** (inside the rdbms block of blog-service.dtrx):
 ```datrix
 entity Comment extends BaseEntity {
 String content;
 belongsTo Post : index;
 belongsTo User as author : index;
 }
 ```

2. **Add Category entity** (inside the same rdbms block):
 ```datrix
 entity Category extends BaseEntity {
 String(100) name : unique;
 String(100) slug : unique;
 }
 ```

3. **Add Tag entity** (inside the same rdbms block):
 ```datrix
 entity Tag extends BaseEntity {
 String(50) name : unique;
 }
 ```

 Then add `resource db.Comment;`, `resource db.Category;`, and `resource db.Tag;` to the rest_api block. See [examples/01-tutorial/05-relationships](../../examples/01-tutorial/05-relationships/) for relationship syntax.

### Generate for Other Languages or Platforms

Language and platform default to values in `system-config.yaml`, with optional CLI overrides:

```yaml
# config/system-config.yaml
test:
  language: python     # or "typescript"
  hosting: docker      # or "kubernetes", "aws", "azure"
```

To switch languages, change the `language` field and regenerate:

```bash
datrix generate --source specs/system.dtrx --output ./generated
```

You can override these values from the command line without editing YAML:

```bash
datrix generate --source specs/system.dtrx --output ./generated --language typescript
datrix generate --source specs/system.dtrx --output ./generated --hosting aws --platform ecs-fargate
```

Install the corresponding generator packages:

```bash
# For TypeScript generation
pip install datrix-codegen-typescript

# For platform configs (Docker, K8s, AWS, Azure)
pip install datrix-codegen-docker datrix-codegen-k8s datrix-codegen-aws datrix-codegen-azure
```

---

## Troubleshooting

### Issue: Import Errors

**Problem:**
```python
ModuleNotFoundError: No module named 'models'
```

**Solution:**
```bash
# Make sure you're in the service directory (e.g. generated/blog-service)
cd generated/blog-service

# Install dependencies
pip install -r requirements.txt

# Run from the correct directory
python -m app.main
```

### Issue: Port Already in Use

**Problem:**
```
ERROR: [Errno 48] Address already in use
```

**Solution:**
```bash
# Use a different port
uvicorn app.main:app --port 8001
```

### Issue: Validation Errors

**Problem:**
```
ParseError: Unexpected token at line 10
```

**Solution:**
- Check your `.dtrx` file syntax
- Make sure all brackets are closed
- Verify entity and service definitions
- Use `datrix validate` to get detailed error messages

---

## Summary

You've successfully:
- ✅ Created a `.dtrx` specification
- ✅ Generated a FastAPI application
- ✅ Run the generated application
- ✅ Tested the API

**What you learned:**
- How to define entities and services in `.dtrx`
- How to generate code with `datrix generate`
- How to run and test generated applications

**Next steps:**
- Explore more examples
- Read the [Architecture Overview](../architecture/architecture-overview.md)
- Read the [Language Reference](../reference/language-reference.md)

---

**Last Updated:** March 16, 2026
