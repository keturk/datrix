import type { EntityManager } from '@mikro-orm/core';
import { Product } from '../ecommerce_product_service/entities/product_db/product.entity';

import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';
import { _getRedis } from '../ecommerce_product_service/_cacheHelpers';
import { producerInstance as mqProducerInstance } from '../mq/producer';

export async function productDbProductAfterUpdate(
  target: Product,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  if (_fieldChanged(target, "inventory", oldValues)) {
    if (mqProducerInstance !== null) {
    await mqProducerInstance.publishInventoryUpdated({ productId: target.id, oldQuantity: _fieldOldValue(target, "inventory", oldValues) as number, newQuantity: target.inventory });
  }
  }
  if (_fieldChanged(target, "status", oldValues)) {
    await _getRedis().del((String("product:") + ':' + String(`product:${target.id}`)));
    await _getRedis().del((String("product:") + ':' + String(`product:slug:${target.slug}`)));
  }
}