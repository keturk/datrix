using System.Collections.Generic;
using System.Threading.Tasks;
using UserService.Data;
using UserService.Messaging.Mq;
using UserService.Messaging;

namespace UserService.Hooks;

internal static class UserDbUserAfterUpdateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::UserService.Models.UserDb.User target,
        UserServiceDbContext db,
        IReadOnlyDictionary<string, object?>? oldValues = null,
        bool commit = true)
    {
        if (!Equals(oldValues["Status"], target.Status)) {
            await AppServiceLocator.GetRequiredService<IMqProducer>().PublishUserStatusChangedAsync(new UserStatusChangedPayload(UserId: target.Id, OldStatus: (global::UserService.Enums.UserStatus)oldValues["Status"]!, NewStatus: target.Status)).ConfigureAwait(false);
            if (((target.Status == global::UserService.Enums.UserStatus.Active) && target.IsVerified)) {
                await AppServiceLocator.GetRequiredService<IMqProducer>().PublishUserVerifiedAsync(new UserVerifiedPayload(UserId: target.Id, Email: target.Email)).ConfigureAwait(false);
            }
        }
    }
}
