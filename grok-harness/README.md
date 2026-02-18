# Grok Harness

Grok-powered browser automation harness for GrokClaw.

## Quick Start

```bash
# Install
pip install grok-harness

# Set API key
export XAI_API_KEY="your-key"

# Run a task
grok-harness agent "check weather in London" --headless

# Help
grok-harness --help
```

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for full usage.

## Security Notes

- Never commit your `.env` or `config.yaml` - they may contain API keys
- API keys are encrypted at rest in Telegram config
- Run `grok-harness setup` for interactive secure configuration
- Copy `.env.example` to `.env` and fill in your values

## Installation

```bash
pip install grok-harness
# Or with embeddings: pip install grok-harness[embeddings]

# Development
pip install -e ".[dev]"
```
