# Grok-Harness Quick Start

## Installation

```bash
# Install from PyPI
pip install grok-harness

# With embeddings support
pip install grok-harness[embeddings]

# Development install
pip install -e ".[dev]"

# Or use Docker
docker build -t grok-harness .
docker run -it grok-harness agent "Hello world"
```

## Configuration

```bash
# Set your Grok API key
export XAI_API_KEY="your-key-here"

# Or create a config file
grok-harness config set grok.api_key your-key-here
grok-harness config set grok.model grok-4-1-fast-reasoning
grok-harness config set browser.headless true
```

## Basic Usage

```bash
# One-line shortcuts
grok-harness weather Pensacola
grok-harness time
grok-harness chat Assistant

# Run a browser agent
grok-harness agent "Get the title from example.com" --headless

# Schedule a daily task
grok-harness schedule add "0 9 * * *" "agent Check weather in London" --name "Daily Weather"

# List scheduled jobs
grok-harness schedule list

# Search memory
grok-harness memory search "prices" --semantic

# Check system health
grok-harness monitor health

# Start interactive mode
grok-harness interactive

# REPL loop (plan, execute, remember)
grok-harness run --interactive
```

## Advanced Features

```bash
# Plan only, no execution
grok-harness agent "Scrape product prices" --dry-run

# Verbose output with full Grok reasoning
grok-harness agent "Monitor prices" -v

# Interactive approval for high-risk actions
grok-harness agent "Run code step" -i

# Save results to file
grok-harness agent "Scrape product prices" --save-results prices.json

# View job details
grok-harness schedule show <job-id>

# Memory stats
grok-harness memory stats

# Clear memory
grok-harness memory clear --type task --force

# Optimization report
grok-harness monitor optimize
```

## System Verification

```bash
# Run complete system verification (no API key required for basic checks)
python scripts/verify_complete_system.py

# With API key for full verification
export XAI_API_KEY=your-key
python scripts/verify_complete_system.py
```

## Docker

```bash
# Build
docker build -t grok-harness .

# Run with API key
docker run -e XAI_API_KEY=your-key grok-harness agent "Get page title" --headless

# Persist config and data
docker run -v grok-data:/home/grok/.grok-harness -e XAI_API_KEY=your-key grok-harness agent "Task"
```

## Summary

Grok-Harness provides:

1. **Intelligent Browser Agent** - Grok-powered autonomous browsing via orchestrator
2. **Persistent Memory** - SQLite + optional embeddings + compression
3. **Smart Scheduler** - Conflict-aware with predictive learning
4. **Safety Guardrails** - Risk classification, approval prompts, retries
5. **Rich CLI** - Live progress, tables, panels
6. **Configuration** - YAML/JSON with auto-detection
7. **Docker Support** - Containerized deployment
