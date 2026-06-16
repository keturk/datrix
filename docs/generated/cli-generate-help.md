<!-- AUTO-GENERATED from `datrix generate --help` — do not edit manually -->
```text
Usage: datrix generate [OPTIONS]                                              
                                                                               
 Generate code from .dtrx files                                                
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│ --source             -s      PATH  .dtrx source files                       │
│ --output             -o      PATH  Output directory (default: ./generated)  │
│ --only                       TEXT  Only generate specified components       │
│                                    (e.g., --only models --only routes). Can │
│                                    be specified multiple times.             │
│ --validation-level   -V      TEXT  Validation thoroughness for generated    │
│                                    code. Levels: none (skip all), fast      │
│                                    (syntax only), standard (syntax + ruff,  │
│                                    default), full (all including pyright +  │
│                                    imports). Development: fast or           │
│                                    --skip-validation; pre-commit: standard; │
│                                    CI/CD: full.                             │
│ --skip-validation    -S            Skip all post-generation validation      │
│                                    (shorthand for --validation-level none)  │
│ --verbose            -v            Show detailed output                     │
│ --watch              -w            Watch for file changes and regenerate    │
│                                    automatically                            │
│ --dry-run            -n            Show what would be generated without     │
│                                    writing files                            │
│ --no-cache                         Disable validation result cache (re-run  │
│                                    all validators)                          │
│ --profile                    TEXT  Config profile for YAML resolution       │
│                                    (e.g., test, development, production).   │
│                                    Default: test                            │
│                                    [default: test]                          │
│ --incremental                      Only generate changed services (requires │
│                                    prior snapshot)                          │
│ --migrations                       Generate migration files from schema     │
│                                    diff                                     │
│ --allow-destructive                Allow destructive migration operations   │
│                                    (e.g. DROP)                              │
│ --service                    TEXT  Generate only for this service           │
│ --migration-format           TEXT  Migration format (raw_sql, alembic,      │
│                                    flyway). Default: raw_sql                │
│                                    [default: raw_sql]                       │
│ --language           -L      TEXT  Override target language from            │
│                                    system .dcfg profile. Valid: python,     │
│                                    typescript                               │
│ --hosting            -H      TEXT  Override hosting platform from           │
│                                    system .dcfg profile. Valid: docker,     │
│                                    aws, azure                               │
│ --platform           -P      TEXT  Override service platform for all        │
│                                    services. Valid: compose, ecs-fargate,   │
│                                    ecs-ec2, lambda, app-runner,             │
│                                    container-apps, functions, app-service   │
│ --help                             Show this message and exit.              │
└─────────────────────────────────────────────────────────────────────────────┘
```
<!-- END AUTO-GENERATED -->
