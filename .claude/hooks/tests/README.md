# Hook Tests

This directory contains tests for the Claude Code hooks.

## Directory Structure

```
hooks/tests/
├── lib/              # Shared test helpers
│   └── test-helpers.sh
├── fixtures/         # Test input fixtures
│   └── inputs/       # JSON input fixtures for various tool types
├── test-*.sh         # Individual test files
└── run-all-tests.sh  # Test runner script
```

## Running Tests

Run all tests:

```bash
./hooks/tests/run-all-tests.sh
```

Run a specific test file:

```bash
./hooks/tests/test-blocking-hooks.sh
```

## Writing Tests

1. Source the test helpers at the top of your test file:

   ```bash
   source "$(dirname "$0")/lib/test-helpers.sh"
   ```

2. Use the provided assertion functions:
   - `assert_eq` - Assert two values are equal
   - `assert_file_exists` - Assert a file exists
   - `assert_json_field` - Assert a JSON field has expected value
   - `assert_exit_code` - Assert a command exits with expected code

3. Name test functions with `test_` prefix.

4. Call `run_tests` at the end of your test file.
