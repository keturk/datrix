#!/bin/bash
# Auto-generated Kafka topic creation script for ecommerce.ShippingService
set -e

KAFKA_BROKER="${KAFKA_BROKER:-ecommerce-shipping-service-mq:9092}"

echo "Creating topic 'ShipmentEvents' (partitions=3, retention=1209600000ms)..."
kafka-topics --bootstrap-server "$KAFKA_BROKER" --create \
  --if-not-exists \
  --topic ShipmentEvents \
  --partitions 3 \
  --replication-factor 1 \
  --config retention.ms=1209600000

echo "All topics created successfully."
