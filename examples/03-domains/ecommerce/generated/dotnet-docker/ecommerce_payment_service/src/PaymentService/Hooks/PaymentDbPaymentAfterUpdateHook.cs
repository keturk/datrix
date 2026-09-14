using PaymentService.Data;
using PaymentService.Messaging.Mq;
using PaymentService.Messaging;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace PaymentService.Hooks;

internal static class PaymentDbPaymentAfterUpdateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::PaymentService.Models.PaymentDb.Payment target,
        PaymentServiceDbContext db,
        IReadOnlyDictionary<string, object?>? oldValues = null,
        bool commit = true)
    {
        if (!Equals(oldValues["Status"], target.Status)) {
            if ((target.Status == global::PaymentService.Enums.PaymentStatus.Completed)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishPaymentProcessedAsync(new PaymentProcessedPayload(PaymentId: target.Id, OrderId: target.OrderId, Amount: target.Amount)).ConfigureAwait(false);
            } else if ((target.Status == global::PaymentService.Enums.PaymentStatus.Failed)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishPaymentFailedAsync(new PaymentFailedPayload(PaymentId: target.Id, OrderId: target.OrderId, Reason: (target.ErrorMessage ?? "Payment failed"))).ConfigureAwait(false);
            } else if ((target.Status == global::PaymentService.Enums.PaymentStatus.Refunded)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishPaymentRefundedAsync(new PaymentRefundedPayload(PaymentId: target.Id, OrderId: target.OrderId, Amount: target.Amount)).ConfigureAwait(false);
            }
        }
    }
}
