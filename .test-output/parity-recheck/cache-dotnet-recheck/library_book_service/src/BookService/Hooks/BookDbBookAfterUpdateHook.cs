using System.Collections.Generic;
using System.Threading.Tasks;
using BookService.Data;
using BookService.Enums;
using BookService.Messaging;
using BookService.Messaging.Mq;
using BookService.Models.BookDb;

namespace BookService.Hooks;

internal static class BookDbBookAfterUpdateHook
{
    internal static async Task ExecuteAsync(
        Book target,
        BookServiceDbContext db,
        IReadOnlyDictionary<string, object?>? oldValues = null,
        bool commit = true
    )
    {
        if (!Equals(oldValues["Status"], target.Status))
        {
            await AppServiceLocator
                .GetRequiredService<MqProducer>()
                .PublishBookStatusChangedAsync(
                    new BookStatusChangedPayload(
                        BookId: target.Id,
                        OldStatus: (BookStatus)oldValues["Status"]!,
                        NewStatus: target.Status
                    )
                )
                .ConfigureAwait(false);
        }
    }
}
