using Microsoft.EntityFrameworkCore;
using ShippingService.Data;
using ShippingService.Messaging.Mq;
using ShippingService.Messaging;
using ShippingService.Models.ShippingDb;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace ShippingService.Hooks;

internal static class ShippingDbShipmentAfterUpdateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::ShippingService.Models.ShippingDb.Shipment target,
        ShippingServiceDbContext db,
        IReadOnlyDictionary<string, object?>? oldValues = null,
        bool commit = true)
    {
        if (!Equals(oldValues["Status"], target.Status)) {
            var shipmentEventEntity = new global::ShippingService.Models.ShippingDb.ShipmentEvent { Shipment = target, Timestamp = DateTimeOffset.UtcNow, Status = target.Status, Location = "System", Description = $"Status updated to {target.Status}" };
            db.ShipmentEvents.Add(shipmentEventEntity);
            await db.SaveChangesAsync();
            if ((target.Status == global::ShippingService.Enums.ShipmentStatus.InTransit)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishShipmentDispatchedAsync(new ShipmentDispatchedPayload(ShipmentId: target.Id, OrderId: target.OrderId, TrackingNumber: target.TrackingNumber)).ConfigureAwait(false);
            } else if ((target.Status == global::ShippingService.Enums.ShipmentStatus.Delivered)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishShipmentDeliveredAsync(new ShipmentDeliveredPayload(ShipmentId: target.Id, OrderId: target.OrderId, DeliveredAt: (target.ActualDelivery ?? DateTimeOffset.UtcNow))).ConfigureAwait(false);
            } else if ((target.Status == global::ShippingService.Enums.ShipmentStatus.Failed)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishShipmentFailedAsync(new ShipmentFailedPayload(ShipmentId: target.Id, OrderId: target.OrderId, Reason: (target.FailureReason ?? "Delivery failed"))).ConfigureAwait(false);
            }
        }
    }
}
