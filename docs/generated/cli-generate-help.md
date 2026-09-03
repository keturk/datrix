<!-- AUTO-GENERATED from `datrix generate --help` — do not edit manually -->
```text
Usage: datrix generate [OPTIONS]                                              
                                                                               
 Generate code from .dtrx files                                                
                                                                               
┌─ Options ───────────────────────────────────────────────────────────────────┐
│    --source                     -s      PATH  .dtrx source files            │
│    --output                     -o      PATH  Output directory (default:    │
│                                               ./generated)                  │
│ *  --language                   -L      TEXT  Target generation language    │
│                                               (e.g. python, typescript,     │
│                                               dotnet, java). Required.      │
│                                               [required]                    │
│    --only                               TEXT  Generate only the named       │
│                                               targets, leaving every other  │
│                                               target's tree and manifest    │
│                                               untouched (e.g. --only        │
│                                               clients, --only docker). A    │
│                                               value is a generation         │
│                                               target's own name, or         │
│                                               'clients' for every activated │
│                                               frontend client target. Can   │
│                                               be specified multiple times.  │
│                                               A partial run plans no        │
│                                               migrations and saves no       │
│                                               incremental snapshot.         │
│    --validation-level           -V      TEXT  Validation thoroughness for   │
│                                               generated code. Levels: none  │
│                                               (skip all post-generation     │
│                                               hooks), fast (import fixing + │
│                                               formatting), standard (fast + │
│                                               the language's validate_files │
│                                               hook; default). Development:  │
│                                               fast or --skip-validation;    │
│                                               pre-commit and CI/CD:         │
│                                               standard.                     │
│    --skip-validation            -S            Skip all post-generation      │
│                                               validation (shorthand for     │
│                                               --validation-level none)      │
│    --verbose                    -v            Show detailed output          │
│    --watch                      -w            Watch for file changes and    │
│                                               regenerate automatically      │
│    --dry-run                    -n            Show what would be generated  │
│                                               without writing files         │
│    --profile                            TEXT  Config profile for ConfigDSL  │
│                                               resolution (e.g., test,       │
│                                               development, production).     │
│                                               Default: test                 │
│                                               [default: test]               │
│    --incremental                              Only generate changed         │
│                                               services (requires prior      │
│                                               snapshot)                     │
│    --migrations                               Generate migration files from │
│                                               schema diff                   │
│    --allow-destructive                        Allow destructive migration   │
│                                               operations (e.g. DROP)        │
│    --service                            TEXT  Generate only for this        │
│                                               service                       │
│    --migration-format                   TEXT  Migration format (raw_sql,    │
│                                               alembic, flyway). Default:    │
│                                               raw_sql                       │
│                                               [default: raw_sql]            │
│    --assert-client-profile-in…                Regenerate the client tree    │
│                                               against every declared        │
│                                               ConfigDSL profile into a      │
│                                               temporary directory and       │
│                                               require byte-identical        │
│                                               MANIFEST.json hashes across   │
│                                               all of them. Fails naming the │
│                                               diverging files if the client │
│                                               surface is not                │
│                                               profile-independent.          │
│                                               Incompatible with --watch and │
│                                               --dry-run.                    │
│    --help                                     Show this message and exit.   │
└─────────────────────────────────────────────────────────────────────────────┘
```
<!-- END AUTO-GENERATED -->
