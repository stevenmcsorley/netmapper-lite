.PHONY: help venv-backend venv-frontend install-backend install-frontend run-helper-dev run-gui-dev test clean

help:
	@echo "NetMapper-Lite Build System"
	@echo ""
	@echo "Targets:"
	@echo "  venv-backend      - Create backend virtual environment"
	@echo "  venv-frontend     - Create frontend virtual environment"
	@echo "  install-backend   - Install backend dependencies"
	@echo "  install-frontend  - Install frontend dependencies"
	@echo "  run-helper-dev    - Run helper in development mode (dev socket)"
	@echo "  run-gui-dev       - Run GTK frontend"
	@echo "  test              - Run test scan"
	@echo "  clean             - Clean build artifacts"

venv-backend:
	python3 -m venv backend/.venv
	@echo "Backend venv created. Activate with: source backend/.venv/bin/activate"

venv-frontend:
	python3 -m venv frontend/.venv
	@echo "Frontend venv created. Activate with: source frontend/.venv/bin/activate"

install-backend: venv-backend
	backend/.venv/bin/pip install --upgrade pip
	backend/.venv/bin/pip install -r backend/requirements.txt
	@echo "Backend dependencies installed"

install-frontend: venv-frontend
	frontend/.venv/bin/pip install --upgrade pip
	frontend/.venv/bin/pip install -r frontend/requirements.txt
	@echo "Frontend dependencies installed"

run-helper-dev:
	@echo "Starting helper in DEV mode (uses /tmp socket)"
	@echo "Note: May require sudo for network scanning capabilities"
	python3 backend/netmapper_helper.py --dev

run-helper-dev-sudo:
	@echo "Starting helper in DEV mode with sudo"
	sudo python3 backend/netmapper_helper.py --dev

run-gui-dev:
	@echo "Starting GTK frontend"
	python3 frontend/gui.py

test:
	@echo "Running integration tests..."
	python3 -m pytest tests/ -v || python3 -m unittest discover tests/ -v

test-lint:
	@echo "Running linting checks..."
	python3 tests/test_linting.py

test-integration:
	@echo "Running integration tests only..."
	python3 -m pytest tests/test_integration.py -v || python3 -m unittest tests.test_integration -v

test-scan-quick:
	@echo "Running quick scan test (requires helper to be running)"
	python3 -c "import socket, json, os; \
	sock_path = '/tmp/netmapper-helper.sock' if os.path.exists('/tmp/netmapper-helper.sock') else '/var/run/netmapper-helper.sock'; \
	s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); \
	s.settimeout(2); \
	s.connect(sock_path); \
	s.sendall(json.dumps({'cmd': 'scan', 'cidr': '192.168.1.0/24'}).encode()); \
	print('Response:', s.recv(4096).decode()); \
	s.close()"

clean:
	rm -rf backend/.venv frontend/.venv
	rm -f /tmp/netmapper-helper.sock
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete"

