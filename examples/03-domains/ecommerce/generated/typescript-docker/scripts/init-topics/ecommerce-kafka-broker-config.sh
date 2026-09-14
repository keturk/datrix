#!/bin/bash
# Auto-generated Kafka broker configuration check for ecommerce-kafka
set -e

KAFKA_BROKER="${KAFKA_BROKER:-ecommerce-kafka:9092}"
OFFSETS_TOPIC='__consumer_offsets'
DECLARED_PARTITIONS='1'
DECLARED_REPLICATION='1'

# offsets.topic.num.partitions and offsets.topic.replication.factor -- emitted on
# the broker container as KAFKA_OFFSETS_TOPIC_NUM_PARTITIONS and
# KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR -- are read ONLY when the broker
# auto-creates its offsets topic, and never again. On a volume where that topic
# already exists (any environment that ran before these settings were declared,
# or before their values changed) the declared values are inert, the deploy is
# green, and nothing else reports the divergence.
#
# This check cannot repair it: Kafka offers no supported way to repartition an
# existing internal topic, so the only route to a different count is destroying
# the log directory, which discards every committed consumer offset. Deciding
# that is a human's call, not a generated script's -- so this reports and exits
# 0 rather than failing the deploy.
echo "Checking $OFFSETS_TOPIC against the declared broker configuration..."

if ! describe="$(kafka-topics --bootstrap-server "$KAFKA_BROKER" --describe --topic "$OFFSETS_TOPIC" 2>/dev/null)" \
    || [ -z "$describe" ]; then
  echo "$OFFSETS_TOPIC does not exist yet; the broker will create it with the declared partitions=$DECLARED_PARTITIONS replicationFactor=$DECLARED_REPLICATION."
  exit 0
fi

live_partitions="$(printf '%s\n' "$describe" | sed -n 's/.*PartitionCount: *\([0-9][0-9]*\).*/\1/p' | head -n 1)"
live_replication="$(printf '%s\n' "$describe" | sed -n 's/.*ReplicationFactor: *\([0-9][0-9]*\).*/\1/p' | head -n 1)"

if [ "$live_partitions" = "$DECLARED_PARTITIONS" ] && [ "$live_replication" = "$DECLARED_REPLICATION" ]; then
  echo "$OFFSETS_TOPIC matches the declared configuration (partitions=$live_partitions, replicationFactor=$live_replication)."
  exit 0
fi

echo "WARNING: $OFFSETS_TOPIC is live with partitions=$live_partitions replicationFactor=$live_replication, but this broker declares partitions=$DECLARED_PARTITIONS replicationFactor=$DECLARED_REPLICATION."
echo "WARNING: Kafka reads offsets.topic.num.partitions and offsets.topic.replication.factor only when it creates $OFFSETS_TOPIC, so the declared values have NOT taken effect on this broker volume."
echo "WARNING: Consequence: this broker keeps the internal-log footprint and per-partition start-up replay cost of its original layout, which is what the declared values were chosen to bound."
echo "WARNING: Remedy: stop the stack and remove the broker's data volume so $OFFSETS_TOPIC is recreated. That discards every committed consumer offset and every unconsumed event on this broker, so consumers resume from their configured auto.offset.reset."
exit 0
