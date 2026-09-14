using ProductService.Cache;
using ProductService.Data;
using ProductService.Messaging.Mq;
using ProductService.Messaging;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

namespace ProductService.Hooks;

internal static class ProductDbProductAfterUpdateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::ProductService.Models.ProductDb.Product target,
        ProductServiceDbContext db,
        IReadOnlyDictionary<string, object?>? oldValues = null,
        bool commit = true)
    {
        if (!Equals(oldValues["Inventory"], target.Inventory)) {
            await AppServiceLocator.GetRequiredService<IMqProducer>().PublishInventoryUpdatedAsync(new InventoryUpdatedPayload(ProductId: target.Id, OldQuantity: (int)oldValues["Inventory"]!, NewQuantity: target.Inventory)).ConfigureAwait(false);
        }
        if (!Equals(oldValues["Status"], target.Status)) {
            await AppServiceLocator.GetRequiredService<ProductCache>().DeleteAllAsync($"product:{target.Id}".ToString());
            await AppServiceLocator.GetRequiredService<ProductCache>().DeleteAllAsync($"product:slug:{target.Slug}".ToString());
        }
    }
}
