using System.Collections.Generic;
using System.Threading.Tasks;
using UserService.Data;

namespace UserService.Hooks;

internal static class UserDbUserBeforeUpdateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::UserService.Models.UserDb.User target,
        UserServiceDbContext db,
        IReadOnlyDictionary<string, object?>? oldValues = null,
        bool commit = true)
    {
        target.UpdatedAt = DateTimeOffset.UtcNow;
    }
}
