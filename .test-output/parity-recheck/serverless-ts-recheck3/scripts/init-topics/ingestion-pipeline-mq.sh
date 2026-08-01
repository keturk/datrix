#!/bin/bash
# Auto-generated Kafka topic creation script for IngestionPipeline
set -e

KAFKA_BROKER="${KAFKA_BROKER:-examples-serverless-demo-system-kafka:9092}"

echo "Creating topic 'ingestion_pipeline.mq.ingestion_events' (partitions=3, retention=604800000ms)..."
kafka-topics --bootstrap-server "$KAFKA_BROKER" --create \
  --if-not-exists \
  --topic ingestion_pipeline.mq.ingestion_events \
  --partitions 3 \
  --replication-factor 1 \
  --config retention.ms=604800000

echo "All topics created successfully."
