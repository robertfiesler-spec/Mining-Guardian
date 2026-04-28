# Mining Guardian Makefile
# Quick commands for development and operations

.PHONY: test test-cov lint clean run scan help pkg pkg-clean

# Default target
help:
	@echo "Mining Guardian - Available Commands"
	@echo "====================================="
	@echo "make test      - Run all tests"
	@echo "make test-cov  - Run tests with coverage"
	@echo "make lint      - Run linter (ruff)"
	@echo "make clean     - Clean pycache and temp files"
	@echo "make run       - Run single scan"
	@echo "make scan      - Alias for run"
	@echo "make services  - Show systemd service status"
	@echo "make logs      - Show recent logs"
	@echo "make pkg       - Build signed + notarized macOS .pkg (Bucket-3, macOS only)"
	@echo "make pkg-clean - Remove build/ directory"

# Testing
test:
	PYTHONPATH=/root/Mining-Guardian pytest tests/ -v

test-cov:
	PYTHONPATH=/root/Mining-Guardian pytest tests/ --cov=core --cov=clients --cov=notifiers --cov=monitoring --cov-report=term-missing

test-quick:
	PYTHONPATH=/root/Mining-Guardian pytest tests/ -q

# Linting (install ruff first: pip install ruff)
lint:
	ruff check core/ clients/ notifiers/ monitoring/ api/ ai/ scripts/

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.bak" -delete 2>/dev/null || true

# Run
run:
	cd /root/Mining-Guardian && source venv/bin/activate && PYTHONPATH=/root/Mining-Guardian python core/mining_guardian.py

scan: run

# Operations
services:
	systemctl status mining-guardian dashboard-api approval-api slack-listener overnight-automation --no-pager | head -50

logs:
	journalctl -u mining-guardian -n 50 --no-pager

db-status:
	sqlite3 /root/Mining-Guardian/guardian.db "SELECT COUNT(*) as scans FROM scans; SELECT COUNT(*) as actions FROM action_audit_log;"

# ---------------------------------------------------------------------------
# macOS .pkg installer build (Bucket-3, Q1 hybrid ~500 MB pkg)
#
# Runs on macOS only — the build host is the operator's Mac with the
# Developer ID Installer cert in its keychain and the .p8 notarization
# private key on disk at the path declared in CREDENTIALS_NOTES.txt.
#
# `make pkg` runs the full 9-step pipeline documented in
# installer/macos-pkg/README.md and implemented in
# installer/macos-pkg/scripts/build_pkg.sh:
#
#   1. Verify Apple Developer cert + notarization credentials reachable
#   2. Refuse to build with a dirty git tree
#   3. Stamp build with current git SHA + version
#   4. Assemble payload (app code + vendored runtime + scripts)
#   5. pkgbuild + productbuild + productsign
#   6. xcrun notarytool submit (with --wait, 30 min timeout)
#   7. xcrun stapler staple + validate
#   8. SHA-256 sidecar + spctl acceptance check
#   9. Print install command
#
# `make pkg-clean` removes the build/ directory.
# ---------------------------------------------------------------------------

pkg:
	@bash installer/macos-pkg/scripts/build_pkg.sh

pkg-clean:
	@rm -rf build/
	@echo "build/ removed"

