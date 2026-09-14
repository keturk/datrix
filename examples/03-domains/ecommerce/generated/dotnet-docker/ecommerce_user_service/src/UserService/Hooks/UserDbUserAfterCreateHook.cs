using System.Collections.Generic;
using System.Threading.Tasks;
using UserService.Data;
using UserService.Integrations;
using UserService.Messaging.Mq;
using UserService.Messaging;

namespace UserService.Hooks;

internal static class UserDbUserAfterCreateHook
{
    internal static async System.Threading.Tasks.Task ExecuteAsync(
        global::UserService.Models.UserDb.User target,
        UserServiceDbContext db,
        bool commit = true)
    {
        await AppServiceLocator.GetRequiredService<IMqProducer>().PublishUserRegisteredAsync(new UserRegisteredPayload(UserId: target.Id, Email: target.Email, FullName: target.FullName)).ConfigureAwait(false);
        await AppServiceLocator.GetRequiredService<IEmailClient>().SendAsync(new System.Text.Json.Nodes.JsonObject { ["to"] = target.Email, ["subject"] = "Verify your email", ["template"] = "emailVerification", ["data"] = new System.Text.Json.Nodes.JsonObject { ["token"] = target.EmailVerificationToken, ["fullName"] = target.FullName } });
    }
}
