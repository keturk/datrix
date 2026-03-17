#!/bin/bash
# Auto-generated Kafka topic creation script for ecommerce.ProductService
set -e

KAFKA_BROKER="${KAFKA_BROKER:-ecommerce-product-service-mq:9092}"

echo "Creating topic 'ProductEvents' (partitions=3, retention=604800000ms)..."
kafka-topics --bootstrap-server "$KAFKA_BROKER" --create \
  --if-not-exists \
  --topic ProductEvents \
  --partitions 3 \
  --replication-factor 1 \
  --config retention.ms=604800000

echo "All topics created successfully."
