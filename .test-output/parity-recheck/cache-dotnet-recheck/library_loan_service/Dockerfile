# Multi-stage build for the service (.NET 10 / ASP.NET Core).
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /app

# Restore first (layer caching) -- csproj is copied alone so dependency
# resolution is cached across source-only changes. Dotnet's generated layout
# nests the .csproj two levels deep (src/{ProjectName}/{ProjectName}.csproj,
# service_project_src_path's own convention) -- unlike python's flat
# pyproject.toml-at-root layout, so both COPY and the restore/publish target
# must reference the nested project path explicitly.
COPY src/LoanService/*.csproj src/LoanService/
RUN dotnet restore src/LoanService/LoanService.csproj

# Copy application source and publish a Release build.
COPY . .
RUN dotnet publish src/LoanService/LoanService.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app

# Copy the published output onto the ASP.NET runtime image.
COPY --from=build /app/publish .

# Set environment variables
ENV PORT=8001
ENV SERVICE_NAME=library-loan-service

# Expose service port
EXPOSE 8001

# Health check: the aspnet runtime image ships no HTTP client binary, so the
# check invokes the app's own --datrix-run healthcheck self-probe instead.
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD dotnet /app/App.dll --datrix-run healthcheck --url http://localhost:8001/live || exit 1

# Run as the non-root "app" user built into the ASP.NET runtime image (.NET 8+).
USER app

# Run the application
CMD ["dotnet", "/app/App.dll"]
