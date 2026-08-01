using System.Collections.Generic;
using System.Threading.Tasks;
using BookService.Data;
using BookService.Enums;
using BookService.Messaging;
using BookService.Messaging.Mq;
using BookService.Models.BookDb;

namespace BookService.Hooks;

internal static class BookDbBookAfterCreateHook
{
    internal static async Task ExecuteAsync(
        Book target,
        BookServiceDbContext db,
        bool commit = true
    )
    {
        target.Status = BookStatus.Available;
        await AppServiceLocator
            .GetRequiredService<MqProducer>()
            .PublishBookAddedAsync(new BookAddedPayload(BookId: target.Id, Title: target.Title))
            .ConfigureAwait(false);
    }
}
