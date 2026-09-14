using OrderService.Data;
using OrderService.Messaging.Mq;
using OrderService.Messaging;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

namespace OrderService.Hooks;

internal static class OrderDbOrderAfterUpdateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::OrderService.Models.OrderDb.Order target,
        OrderServiceDbContext db,
        IReadOnlyDictionary<string, object?>? oldValues = null,
        bool commit = true)
    {
        if (!Equals(oldValues["Status"], target.Status)) {
            await AppServiceLocator.GetRequiredService<IMqProducer>().PublishOrderStatusChangedAsync(new OrderStatusChangedPayload(OrderId: target.Id, OldStatus: (global::OrderService.Enums.OrderStatus)oldValues["Status"]!, NewStatus: target.Status)).ConfigureAwait(false);
            if ((target.Status == global::OrderService.Enums.OrderStatus.Confirmed)) {
                List<JsonNode> orderItems = target.Items.Select((i) => new System.Text.Json.Nodes.JsonObject { ["productId"] = i.ProductId, ["quantity"] = i.Quantity }).Cast<System.Text.Json.Nodes.JsonNode>().ToList();
                double estimatedWeight = (target.Items.Count * 1.0);
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishOrderConfirmedAsync(new OrderConfirmedPayload(OrderId: target.Id, PaymentId: target.PaymentId, ReservationId: target.InventoryReservationId, ShippingAddress: target.ShippingAddress, Items: orderItems, EstimatedWeight: Convert.ToDecimal(estimatedWeight, CultureInfo.InvariantCulture))).ConfigureAwait(false);
            } else if ((target.Status == global::OrderService.Enums.OrderStatus.Cancelled)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishOrderCancelledAsync(new OrderCancelledPayload(OrderId: target.Id, Reason: (target.CancellationReason ?? "Cancelled"), ReservationId: target.InventoryReservationId)).ConfigureAwait(false);
            }
        }
    }
}
