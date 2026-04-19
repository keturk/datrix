#!/bin/sh
set -e
mc alias set local http://ecommerce-product-service-minio:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
mc mb local/ecommerce-products --ignore-existing
echo "Bucket ecommerce-products created successfully"
