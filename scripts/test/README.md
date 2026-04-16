# Test Scripts

Test execution and status reporting scripts.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/test/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `test.ps1` | Main test runner for projects |
| `run-complete.ps1` | Run complete test suite |
| `status-tests.ps1` | Show test status summary |
| `status-unit-tests.ps1` | Show running test status |
| `status-deploy-tests.ps1` | Show deployment test status |
| `cleanup.ps1` | Clean up test artifacts |

## test.ps1

Main test runner for one or more Datrix projects.

### Basic Usage

```powershell
# Test a single project
.\test.ps1 datrix-common

# Test using folder path
.\test.ps1 .\datrix-common\

# Test multiple projects
.\test.ps1 datrix-common datrix-language

# Test all projects
.\test.ps1 -All
```

### Test Type Filters

```powershell
# Run only unit tests
.\test.ps1 datrix-common -Unit

# Run only integration tests
.\test.ps1 datrix-common -Integration

# Run only end-to-end tests
.\test.ps1 datrix-common -E2E

# Run fast tests (excludes slow)
.\test.ps1 datrix-common -Fast

# Run slow tests only
.\test.ps1 datrix-common -Slow
```

### Test Selection

```powershell
# Run specific test file
.\test.ps1 datrix-common -Specific "tests/unit/test_parser.py"

# Run tests matching keyword
.\test.ps1 datrix-language -Keyword "test_basic"
```

### Options

```powershell
# With coverage report
.\test.ps1 datrix-common -Coverage

# Verbose output
.\test.ps1 datrix-common -VerboseOutput

# Don't save logs
.\test.ps1 datrix-common -NoSave

# Skip dependency installation
.\test.ps1 datrix-common -SkipInstall

# Debug mode
.\test.ps1 datrix-common -Dbg
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `-Projects` | Project names or paths (positional) |
| `-All` | Test all projects |
| `-Coverage` | Generate coverage reports |
| `-VerboseOutput` | Enable verbose test output |
| `-NoSave` | Don't save output to log files |
| `-NoAutoInstall` | Prompt for dependency installation |
| `-SkipInstall` | Skip dependency installation |
| `-Unit` | Run unit tests only |
| `-Integration` | Run integration tests only |
| `-E2E` | Run end-to-end tests only |
| `-Fast` | Run fast tests only |
| `-Slow` | Run slow tests only |
| `-Specific` | Run specific test file/pattern |
| `-Keyword` | Filter tests by keyword (-k) |
| `-Dbg` | Enable debug logging |

### Output

Test results are saved to `<project>/.test_results/test-results-TIMESTAMP.log`.

The summary shows:
- Pass/fail status per project
- Test counts (passed, failed, skipped, etc.)
- AI prompt for fixing failures (appended to log)

## run-complete.ps1

Runs the complete test suite with generation and validation.

```powershell
.\run-complete.ps1
```

## status-tests.ps1

Shows a summary of test status across projects.

```powershell
.\status-tests.ps1
```

## cleanup.ps1

Cleans up test artifacts (.test_results, __pycache__, .pytest_cache).

```powershell
.\cleanup.ps1
```
