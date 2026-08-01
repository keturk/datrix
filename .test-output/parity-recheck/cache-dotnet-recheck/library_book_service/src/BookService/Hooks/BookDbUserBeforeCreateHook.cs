using System.Collections.Generic;
using System.Threading.Tasks;
using BookService.Data;
using BookService.Enums;
using BookService.Models.BookDb;

namespace BookService.Hooks;

internal static class BookDbUserBeforeCreateHook
{
    internal static async Task ExecuteAsync(
        User target,
        BookServiceDbContext db,
        bool commit = true
    )
    {
        target.PasswordHash = BCrypt.Net.BCrypt.HashPassword(target.PasswordHash);
    }
}
