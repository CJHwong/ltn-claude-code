# ltn-claude-code

Use [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI as the LLM backend for [lazy-take-notes](https://github.com/CJHwong/lazy-take-notes).

Replaces Ollama/OpenAI with Claude Code for digest summaries and quick actions. All TUI features work out of the box.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude` on PATH)
- [lazy-take-notes](https://github.com/CJHwong/lazy-take-notes) v0.1.0+

## Installation

If you have `take-note` installed via [lazy-take-notes setup](https://github.com/CJHwong/lazy-take-notes), update the wrapper script to include the plugin:

```bash
cat > "$(brew --prefix)/bin/take-note" << 'EOF'
#!/bin/bash
exec uvx --from "git+https://github.com/CJHwong/lazy-take-notes.git" \
    --with "ltn-claude-code @ git+https://github.com/CJHwong/ltn-claude-code.git" \
    lazy-take-notes "$@"
EOF
chmod +x "$(brew --prefix)/bin/take-note"
```

## Setup

1. Launch the app and open **Settings** (or run `lazy-take-notes config`)
2. In the **AI Provider** tab, select **claude-code** from the dropdown
3. Save and start a session as usual

The model fields are hidden when claude-code is selected since models are configured separately.

### Plugin config

Advanced settings go in `config.yaml` under the `claude_code` key:

```yaml
llm_provider: claude-code
claude_code:
  digest_model: sonnet      # model for rolling summaries (default: sonnet)
  interactive_model: haiku   # model for quick actions (default: haiku)
  budget: 1.0               # max USD per session (default: 1.0)
```

## How it works

1. Shells out to `claude --print --output-format json` for each LLM call
2. Maintains conversation history via `--session-id` (create) / `--resume` (continue)
3. Serializes concurrent calls with an asyncio lock to prevent session conflicts
4. Extracts system prompts from the message list and passes them via `--append-system-prompt`
5. Runs Claude Code from a temp directory to avoid picking up project CLAUDE.md files

## Development

```bash
git clone https://github.com/CJHwong/ltn-claude-code.git
cd ltn-claude-code
uv sync

# Run from local source
uv run lazy-take-notes record

# Run tests
uv run pytest tests/ -v
```

## License

MIT
