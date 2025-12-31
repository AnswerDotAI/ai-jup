# ai-jup development commands

# Default recipe - show available commands
default:
    @just --list

# Run all tests: mocks first (fast), then live kernel tests
# Automatically starts a test server on a free port, then stops it when done
test:
    #!/usr/bin/env bash
    set -e
    
    echo "═══════════════════════════════════════════════════════════"
    echo "  PHASE 1: Fast tests (mocks + unit tests) in parallel"
    echo "═══════════════════════════════════════════════════════════"
    
    # Create temp files for output
    ts_log=$(mktemp)
    py_mock_log=$(mktemp)
    
    # Run TypeScript and Python mock tests in parallel
    yarn test > "$ts_log" 2>&1 &
    ts_pid=$!
    
    # Mock/unit tests only - no live kernel needed
    python -m pytest tests/test_handlers.py tests/test_parser.py \
        tests/test_api_integration.py tests/test_kernel_integration.py \
        -v > "$py_mock_log" 2>&1 &
    py_mock_pid=$!
    
    # Wait for both
    ts_exit=0
    py_mock_exit=0
    wait $ts_pid || ts_exit=$?
    wait $py_mock_pid || py_mock_exit=$?
    
    echo ""
    echo "--- TypeScript Tests (Jest) ---"
    cat "$ts_log"
    
    echo ""
    echo "--- Python Mock/Unit Tests ---"
    cat "$py_mock_log"
    
    rm -f "$ts_log" "$py_mock_log"
    
    if [ $ts_exit -ne 0 ] || [ $py_mock_exit -ne 0 ]; then
        echo ""
        echo "❌ Phase 1 failed. Stopping before live tests."
        exit 1
    fi
    
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  PHASE 2: Live kernel tests (auto-managed test server)"
    echo "═══════════════════════════════════════════════════════════"
    
    # Find an available port dynamically
    TEST_PORT=$(python -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")
    TEST_TOKEN="test-token-$$"
    
    echo "Starting test server on port $TEST_PORT..."
    
    # Start Jupyter server in background
    jupyter lab --port=$TEST_PORT --no-browser --ServerApp.token=$TEST_TOKEN \
        > ".jupyter-test-$TEST_PORT.log" 2>&1 &
    SERVER_PID=$!
    
    # Wait for server to be ready (max 30 seconds)
    for i in {1..30}; do
        if curl -s "http://localhost:$TEST_PORT/api/status?token=$TEST_TOKEN" > /dev/null 2>&1; then
            echo "✓ Server ready on port $TEST_PORT (PID $SERVER_PID)"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "❌ Server failed to start within 30 seconds"
            kill $SERVER_PID 2>/dev/null || true
            rm -f ".jupyter-test-$TEST_PORT.log"
            exit 1
        fi
        sleep 1
    done
    
    # Run live kernel tests with the dynamic port
    test_exit=0
    JUPYTER_BASE_URL="http://localhost:$TEST_PORT" JUPYTER_TOKEN="$TEST_TOKEN" \
        python -m pytest tests/test_live_kernel.py tests/test_tool_execute_handler.py \
            tests/test_solveit_flow.py tests/test_tool_loop.py \
            --ignore=tests/test_fastcore_tools_integration.py \
            -v || test_exit=$?
    
    # Clean up: stop the test server
    echo ""
    echo "Stopping test server (PID $SERVER_PID)..."
    kill $SERVER_PID 2>/dev/null || true
    wait $SERVER_PID 2>/dev/null || true
    rm -f ".jupyter-test-$TEST_PORT.log"
    
    if [ $test_exit -ne 0 ]; then
        echo "❌ Live kernel tests failed."
        exit 1
    fi
    
    echo ""
    echo "✅ All tests passed!"

# Run TypeScript tests with Jest
test-ts:
    yarn test

# Run Python tests (excluding LLM and E2E tests that need special setup)
test-py:
    python -m pytest tests/ -v \
        --ignore=tests/test_e2e_playwright.py \
        --ignore=tests/test_haiku_integration.py \
        --ignore=tests/test_solveit_flow.py \
        --ignore=tests/test_fastcore_tools_integration.py

# Run Python tests with LLM integration (requires ANTHROPIC_API_KEY)
test-llm:
    python -m pytest tests/test_haiku_integration.py tests/test_solveit_flow.py -v

# Run all Python tests including live kernel tests
test-py-all:
    python -m pytest tests/ -v --ignore=tests/test_e2e_playwright.py

# Type check TypeScript
check-types:
    npx tsc --noEmit

# Build the extension (development mode)
build: build-ts build-ext

# Build TypeScript
build-ts:
    npx tsc --sourceMap

# Build the JupyterLab extension
build-ext:
    jupyter labextension build --development True .

# Build for production
build-prod:
    npx tsc
    jupyter labextension build .

# Clean build artifacts
clean:
    rm -rf lib/ ai_jup/labextension/ tsconfig.tsbuildinfo
    rm -rf dist/ *.egg-info/

# Install extension into JupyterLab (development mode with live reload)
install: build
    pip install -e ".[test]"
    jupyter labextension develop . --overwrite
    @echo ""
    @echo "✅ Extension installed! Restart JupyterLab to activate."

# Install extension (production mode, no source link)
install-prod: build-prod
    pip install .
    @echo ""
    @echo "✅ Extension installed! Restart JupyterLab to activate."

# Uninstall extension
uninstall:
    pip uninstall -y ai_jup
    jupyter labextension uninstall ai-jup 2>/dev/null || true
    @echo "✅ Extension uninstalled."

# Start JupyterLab for testing
lab:
    jupyter lab --no-browser

# Start Jupyter server for API testing
server:
    jupyter lab --no-browser --ServerApp.token=debug-token

# ===== PyPI Publishing =====

# Build distribution packages
dist: clean build-prod
    python -m build

# Check distribution with twine
dist-check: dist
    twine check dist/*

# Upload to TestPyPI (for testing)
publish-test: dist-check
    twine upload --repository testpypi dist/*

# Bump minor version, build, and upload to PyPI
publish:
    #!/usr/bin/env bash
    set -e
    
    # Get current version and bump patch
    current=$(jq -r '.version' package.json)
    IFS='.' read -r major minor patch <<< "$current"
    new_version="$major.$minor.$((patch + 1))"
    
    echo "Bumping version: $current -> $new_version"
    
    # Update package.json
    jq --arg v "$new_version" '.version = $v' package.json > package.json.tmp
    mv package.json.tmp package.json
    
    # Clean, build, and check
    just clean
    just build-prod
    python -m build
    twine check dist/*
    
    # Commit version bump
    git add package.json
    git commit -m "Release v$new_version"
    git tag "v$new_version"
    
    # Upload to PyPI
    twine upload dist/*
    
    echo ""
    echo "✅ Published v$new_version to PyPI"
    echo "   Don't forget to push: git push && git push --tags"

# Full release workflow: test, build, check, publish to PyPI
release: test dist-check
    twine upload dist/*

# Dry-run release: test, build, check (no upload)
release-check: test dist-check
    @echo "✅ Ready to publish. Run 'just release' to upload to PyPI."

# ===== Utilities =====

# Format Python code
fmt:
    ruff format ai_jup/ tests/

# Lint Python code
lint:
    ruff check ai_jup/ tests/

# Watch TypeScript for changes
watch:
    npx tsc -w --sourceMap

# ===== E2E Tests (Galata/Playwright) =====

# Run Galata E2E tests (requires no running Jupyter server on 8888)
test-e2e:
    yarn test:e2e

# Run Galata E2E tests in headed mode (visible browser)
test-e2e-headed:
    yarn test:e2e -- --headed

# Run a specific E2E test by name pattern
test-e2e-grep PATTERN:
    yarn test:e2e -- --grep "{{PATTERN}}"

# Update E2E visual snapshots
test-e2e-update:
    yarn test:e2e:update

# Show E2E test report
test-e2e-report:
    npx playwright show-report
