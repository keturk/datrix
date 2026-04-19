#!/bin/bash
# Auto-generated Kafka topic creation script for ecommerce.OrderService
set -e

KAFKA_BROKER="${KAFKA_BROKER:-ecommerce-order-service-mq:9092}"

echo "Creating topic 'OrderEvents' (partitions=6, retention=1209600000ms)..."
kafka-topics --bootstrap-server "$KAFKA_BROKER" --create \
  --if-not-exists \
  --topic OrderEvents \
  --partitions 6 \
  --replication-factor 1 \
  --config retention.ms=1209600000

echo "All topics created successfully."
