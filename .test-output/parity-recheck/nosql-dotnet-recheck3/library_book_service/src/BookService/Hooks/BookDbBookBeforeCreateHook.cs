using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading.Tasks;
using BookService.Data;
using BookService.Enums;
using BookService.Models.BookDb;

namespace BookService.Hooks;

internal static class BookDbBookBeforeCreateHook
{
    internal static async Task ExecuteAsync(
        Book target,
        BookServiceDbContext db,
        bool commit = true
    )
    {
        target.CatalogNumber =
            $"CAT-{new string(Enumerable.Range(0, 8).Select(_ => "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"[Random.Shared.Next(62)]).ToArray()).ToUpperInvariant()}";
    }
}
