// Idempotent MongoDB index provisioning for service library.BookService (block docdb).
// Run with: mongosh "<connection-uri>" 01_create_indexes.js
// createIndex is idempotent: re-running this script never duplicates an index.
const db = db.getSiblingDB("docdb");
db.getCollection("reading_activity").createIndex(
  { "book_id": 1 },
  { name: "reading_activity_book_id_idx", unique: false }
);
db.getCollection("reading_activity").createIndex(
  { "member_id": 1 },
  { name: "reading_activity_member_id_idx", unique: false }
);
db.getCollection("reading_activity").createIndex(
  { "book_id": 1, "timestamp": 1 },
  { name: "reading_activity_book_id_timestamp_idx", unique: false }
);
db.getCollection("reading_activity").createIndex(
  { "member_id": 1, "timestamp": 1 },
  { name: "reading_activity_member_id_timestamp_idx", unique: false }
);
db.getCollection("book_rating").createIndex(
  { "book_id": 1 },
  { name: "book_rating_book_id_idx", unique: false }
);
db.getCollection("book_rating").createIndex(
  { "member_id": 1 },
  { name: "book_rating_member_id_idx", unique: false }
);
db.getCollection("book_rating").createIndex(
  { "book_id": 1, "created_at": 1 },
  { name: "book_rating_book_id_created_at_idx", unique: false }
);
