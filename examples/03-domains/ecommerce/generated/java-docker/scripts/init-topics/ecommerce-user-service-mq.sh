#!/bin/bash
# Auto-generated Kafka topic setup script for ecommerce.UserService
set -e

KAFKA_BROKER="${KAFKA_BROKER:-ecommerce-kafka:9092}"

# `kafka-topics --create --if-not-exists` honours --config only on the run that
# actually creates the topic. On every later run an existing topic keeps the
# retention it was born with, so a changed `retention` in the source definition
# would never reach it and the declared value would read as active while doing
# nothing. `kafka-configs --alter` is idempotent and applies in both cases, so
# the declared retention converges rather than only being seeded.
#
# Partition count and replication factor cannot converge the same way: Kafka can
# only RAISE a partition count, and raising it rewrites the key->partition
# mapping that ordering and compaction depend on. So a divergence there is
# reported and left alone -- the remedy discards data and is a human decision.
setup_topic() {
  topic="$1"
  partitions="$2"
  replication="$3"
  retention_ms="$4"

  echo "Configuring topic '$topic' (partitions=$partitions, replicationFactor=$replication, retention=${retention_ms}ms)..."
  kafka-topics --bootstrap-server "$KAFKA_BROKER" --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor "$replication" \
    --config "retention.ms=$retention_ms"

  kafka-configs --bootstrap-server "$KAFKA_BROKER" --alter \
    --entity-type topics \
    --entity-name "$topic" \
    --add-config "retention.ms=$retention_ms"

  describe="$(kafka-topics --bootstrap-server "$KAFKA_BROKER" --describe --topic "$topic")"
  live_partitions="$(printf '%s\n' "$describe" | sed -n 's/.*PartitionCount: *\([0-9][0-9]*\).*/\1/p' | head -n 1)"
  live_replication="$(printf '%s\n' "$describe" | sed -n 's/.*ReplicationFactor: *\([0-9][0-9]*\).*/\1/p' | head -n 1)"
  if [ "$live_partitions" != "$partitions" ] || [ "$live_replication" != "$replication" ]; then
    echo "WARNING: topic '$topic' is live with partitions=$live_partitions replicationFactor=$live_replication, but this configuration declares partitions=$partitions replicationFactor=$replication."
    echo "WARNING: Kafka reads both only when it creates a topic, so the declared values have NOT taken effect on this broker volume."
    echo "WARNING: Remedy: delete and recreate '$topic' (this discards every event it still retains), or change the declaration to match what is live."
  fi
}

setup_topic 'ecommerce_user_service.mq.user_events' '3' '1' '604800000'
echo "All topics configured successfully."
