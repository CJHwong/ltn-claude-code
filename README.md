# ltn-claude-code

Use [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI as the LLM backend for [lazy-take-notes](https://github.com/CJHwong/lazy-take-notes).

Replaces Ollama/OpenAI with Claude Code for digest summaries and quick actions. All TUI features work out of the box.

## Usage

```bash
uvx --from "lazy-take-notes @ git+https://github.com/CJHwong/lazy-take-notes.git" \
    --with "ltn-claude-code @ git+https://github.com/CJHwong/ltn-claude-code.git" \
    lazy-take-notes record
```

If you have `take-note` installed via [lazy-take-notes setup](https://github.com/CJHwong/lazy-take-notes), you can add the plugin permanently by updating the wrapper script:

```bash
cat > "$(brew --prefix)/bin/take-note" << 'EOF'
#!/bin/bash
exec uvx --from "git+https://github.com/CJHwong/lazy-take-notes.git" \
    --with "ltn-claude-code @ git+https://github.com/CJHwong/ltn-claude-code.git" \
    lazy-take-notes "$@"
EOF
chmod +x "$(brew --prefix)/bin/take-note"
```

## Configuration

Set the provider in `config.yaml` (open with `lazy-take-notes config`):

```yaml
llm_provider: claude-code
claude_code:
  digest_model: sonnet      # model for rolling summaries (default: sonnet)
  interactive_model: haiku   # model for quick actions (default: haiku)
  budget: 1.0               # max USD per session (default: 1.0)
```

Or select "claude-code" from the AI Provider dropdown in the settings TUI.

## How it works

1. Shells out to `claude --print --output-format json` for each LLM call
2. Maintains conversation history via `--session-id` (create) / `--resume` (continue)
3. Serializes concurrent calls with an asyncio lock to prevent session conflicts
4. Extracts system prompts from the message list and passes them via `--append-system-prompt`
5. Runs Claude Code from a temp directory to avoid picking up project CLAUDE.md files

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated (`claude` on PATH)
- [lazy-take-notes](https://github.com/CJHwong/lazy-take-notes) v0.1.0+

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
