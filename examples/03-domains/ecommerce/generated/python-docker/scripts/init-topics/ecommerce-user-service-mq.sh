#!/bin/bash
# Auto-generated Kafka topic creation script for ecommerce.UserService
set -e

KAFKA_BROKER="${KAFKA_BROKER:-ecommerce-user-service-mq:9092}"

echo "Creating topic 'UserEvents' (partitions=3, retention=604800000ms)..."
kafka-topics --bootstrap-server "$KAFKA_BROKER" --create \
  --if-not-exists \
  --topic UserEvents \
  --partitions 3 \
  --replication-factor 1 \
  --config retention.ms=604800000

echo "All topics created successfully."
