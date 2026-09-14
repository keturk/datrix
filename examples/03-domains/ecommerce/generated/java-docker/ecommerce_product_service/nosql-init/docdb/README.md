# NoSQL Index Provisioning - ecommerce.ProductService

These artifacts provision NoSQL indexes for the `docdb` block
(engine: `mongodb`). They are generated separately from the relational
`db-init/` scripts and live under `nosql-init/`.

## MongoDB

`01_create_indexes.js` creates 6 index(es) using
`db.collection.createIndex()`. The script is idempotent: `createIndex`
never duplicates an existing index, so the script is safe to re-run.

Apply it with:

```bash
mongosh "<connection-uri>" 01_create_indexes.js
```
