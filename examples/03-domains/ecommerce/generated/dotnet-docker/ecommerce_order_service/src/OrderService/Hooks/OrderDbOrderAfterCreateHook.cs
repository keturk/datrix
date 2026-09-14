using OrderService.Clients;
using OrderService.Data;
using OrderService.Messaging.Mq;
using OrderService.Messaging;
using OrderService.Queue;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace OrderService.Hooks;

internal static class OrderDbOrderAfterCreateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::OrderService.Models.OrderDb.Order target,
        OrderServiceDbContext db,
        bool commit = true)
    {
        await AppServiceLocator.GetRequiredService<IMqProducer>().PublishOrderCreatedAsync(new OrderCreatedPayload(OrderId: target.Id, OrderNumber: target.OrderNumber, CustomerId: target.CustomerId, Total: target.Total, ReservationId: target.InventoryReservationId)).ConfigureAwait(false);
        await AppServiceLocator.GetRequiredService<RabbitMqQueueClient>().DispatchProcessPaymentAsync(target.Id, target.Total, "usd").ConfigureAwait(false);
        global::OrderService.Clients.User u = await AppServiceLocator.GetRequiredService<UserServiceClient>().GetAsync<User>($"/api/v1/service/{target.CustomerId}");
        await AppServiceLocator.GetRequiredService<RabbitMqQueueClient>().DispatchSendOrderConfirmationAsync(target.Id, u.Email, target.OrderNumber).ConfigureAwait(false);
    }
}
