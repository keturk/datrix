// Idempotent MongoDB index provisioning for service ecommerce.ProductService (block docdb).
// Run with: mongosh "<connection-uri>" 01_create_indexes.js
// createIndex is idempotent: re-running this script never duplicates an index.
const db = db.getSiblingDB("product_analytics");
db.getCollection("product_review").createIndex(
  { "product_id": 1 },
  { name: "product_review_product_id_idx", unique: false }
);
db.getCollection("product_review").createIndex(
  { "user_id": 1 },
  { name: "product_review_user_id_idx", unique: false }
);
db.getCollection("product_review").createIndex(
  { "product_id": 1, "created_at": 1 },
  { name: "product_review_product_id_created_at_idx", unique: false }
);
db.getCollection("product_review").createIndex(
  { "user_id": 1, "created_at": 1 },
  { name: "product_review_user_id_created_at_idx", unique: false }
);
db.getCollection("product_analytics").createIndex(
  { "product_id": 1 },
  { name: "product_analytics_product_id_idx", unique: false }
);
db.getCollection("product_analytics").createIndex(
  { "product_id": 1, "event_type": 1, "timestamp": 1 },
  { name: "product_analytics_product_id_event_type_timestamp_idx", unique: false }
);
