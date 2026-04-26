# Mining Guardian Makefile
# Quick commands for development and operations

.PHONY: test test-cov lint clean run scan help

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
