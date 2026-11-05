# Coldframe

Cold-storage monitoring built as a complete application: every fridge in a chain of cold stores reports its temperature, a reading out of range opens an alert and pages someone, a technician takes it and says what they fixed, and new firmware rolls out a few devices at a time. The devices and the paging vendor run as mocks in the same stack, and the simulated fleet really does send readings every minute, so nothing here needs hardware or an account with anyone. Coldframe is invented.

## What it shows

| Feature | Where |
|---|---|
| Two apps for two audiences, one on web and mobile | [operations-app.dtrx](operations-app.dtrx), [technician-app.dtrx](technician-app.dtrx) |
| One database per kind of data: a document store for readings, a cache for the latest one, relational for alerts | `nosql docdb`, `cache redis` and `rdbms alertDb` in [telemetry-service.dtrx](telemetry-service.dtrx) |
| A device reporting with its own API key, of which only the hash is stored | `DeviceIngestAPI` in [telemetry-service.dtrx](telemetry-service.dtrx), [config/identity/device-keys.dcfg](config/identity/device-keys.dcfg) |
| One alert per problem, so a warm fridge pages once and not every minute | `openAlert` in [telemetry-service.dtrx](telemetry-service.dtrx) |
| A row lock so two technicians cannot take one alert | `claim` in [telemetry-service.dtrx](telemetry-service.dtrx) |
| A job that notices silence, and an event that turns it into an alert | `MarkOffline` in [device-service.dtrx](device-service.dtrx), `subscribe DeviceEvents` in [telemetry-service.dtrx](telemetry-service.dtrx) |
| A rollout that stops itself when too many devices refuse | `AdvanceRollouts` in [firmware-service.dtrx](firmware-service.dtrx) |
| A socket that answers with the latest reading | `LiveFeed` in [telemetry-service.dtrx](telemetry-service.dtrx) |
| A map, a line chart and a bar chart | `Sites`, `DeviceReadings` and `Overview` in [operations-app.dtrx](operations-app.dtrx) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| A simulator you can break on purpose | [mocks/fleet-mock.dtrx](mocks/fleet-mock.dtrx) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Operations app | 4200 | The overview, sites, devices, alerts, firmware and the simulator |
| Technician app | 4300 | The queue, an alert, and where the sites are. Also generated as a Flutter app |
| `DeviceService` | 8001 | Sites and devices, and the application's identity block |
| `TelemetryService` | 8002 | Readings and alerts |
| `FirmwareService` | 8003 | Releases and rollouts |
| `FleetMock` | 8090 | Stands in for the devices and their command gateway |
| `PagerMock` | 8091 | Stands in for the paging vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `FleetProvider` | `FleetMock` | Queues a command and applies it at the next tick. A device that is unplugged, or set to refuse, rejects it with a reason. Every powered device sends a reading each minute |
| `PagerProvider` | `PagerMock` | Keeps every page in a log the Operations app shows. Nobody's phone rings |

## Run it

```bash
datrix generate -s examples/03-domains/iot-platform/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Operations: <http://localhost:4200>
- Technician: <http://localhost:4300>

## Things to try

1. **Watch it come alive.** A minute after the stack is up, the seeded devices go from Provisioning to Online and their charts start to fill.
2. **Open a door.** As `operator`, open the Simulated fleet page and open the Dairy fridge's door. At the next reading it is 9 degrees warmer: an alert opens, and the Pages sent page shows one page, however many readings follow.
3. **Fix it.** As `technician`, take the alert in the Technician app and mark it fixed, saying what you did. Have two people press Take this together, and one of them is told it has gone.
4. **Close the door without anyone stepping in.** Open a door, close it again before anyone takes the alert, and the alert resolves itself at the next reading.
5. **Pull a plug.** Unplug a device. After five silent minutes it counts as offline, which raises its own alert. Plug it back in and that alert closes.
6. **Roll out firmware.** As `opsLead`, start a rollout of 1.5.0. Two devices get it each minute. The Vegetable room refuses, and you can follow each device on the rollout's page. Unplug a second device first, and two refusals stop the rollout until you resume it.
7. **Be a real device.** A device can report for itself, with the development key the seed holds the hash of:

   ```bash
   curl -X POST http://localhost:8080/api/v1/ingest/readings \
     -H 'X-Device-Key: dev-only-device-key-not-a-credential' \
     -H 'Content-Type: application/json' \
     -d '{"serialNumber": "CF-1001", "temperature": 12.5}'
   ```

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can create a sign-in and it reaches nothing. `opsLead`, `technician` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `coldframe-identity` project.

The simulator, commands and pages sent need `operator`. Firmware needs `opsLead`.

## The development keys

`config/*-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

This is an example and not a food safety system: the temperature ranges are invented, and nothing here has been assessed against any cold-chain regulation.
