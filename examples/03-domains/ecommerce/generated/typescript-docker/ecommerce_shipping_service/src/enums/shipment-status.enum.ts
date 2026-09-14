export enum ShipmentStatus {
  Pending = 'pending',
  PickedUp = 'picked_up',
  InTransit = 'in_transit',
  OutForDelivery = 'out_for_delivery',
  Delivered = 'delivered',
  Failed = 'failed',
  Returned = 'returned',
}
import { BadRequestException } from '@nestjs/common';

export namespace ShipmentStatus {
  // A Map, never an object literal: `{}[s]` resolves through Object.prototype, so a
  // lookup of 'constructor' / 'toString' / '__proto__' would return a prototype member
  // instead of missing, and the classifier would hand back a non-member typed as
  // ShipmentStatus rather than throwing or returning the fallback. The argument is
  // untrusted, so the lookup must only ever see declared keywords.
  const EQUAL_KEYWORDS: ReadonlyMap<string, ShipmentStatus> = new Map<string, ShipmentStatus>([
    ['PU', ShipmentStatus.PickedUp],
    ['IT', ShipmentStatus.InTransit],
    ['OD', ShipmentStatus.OutForDelivery],
    ['DL', ShipmentStatus.Delivered],
    ['DE', ShipmentStatus.Failed],
  ]);

  const CONTAINS_KEYWORDS: ReadonlyArray<readonly [string, ShipmentStatus]> = [
    ['PU', ShipmentStatus.PickedUp],
    ['IT', ShipmentStatus.InTransit],
    ['OD', ShipmentStatus.OutForDelivery],
    ['DL', ShipmentStatus.Delivered],
    ['DE', ShipmentStatus.Failed],
  ];

  export function equalsKeyword(s: string, fallback?: ShipmentStatus): ShipmentStatus {
    const hit = EQUAL_KEYWORDS.get(s);
    if (hit !== undefined) {
      return hit;
    }
    if (fallback !== undefined) {
      return fallback;
    }
    throw new BadRequestException('Unrecognized ShipmentStatus value.');
  }

  export function containsKeyword(s: string, fallback?: ShipmentStatus): ShipmentStatus {
    for (const [kw, member] of CONTAINS_KEYWORDS) {
      if (s.includes(kw)) {
        return member;
      }
    }
    if (fallback !== undefined) {
      return fallback;
    }
    throw new BadRequestException('Unrecognized ShipmentStatus value.');
  }
}
