# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-20

### Added

- Core JSON-to-Markdown converter for Gemini AI Studio exports
- HTML export with dark/light mode support (`--html`)
- JSONL fine-tuning dataset export (`--to-jsonl`)
- Interactive Table of Contents generation (`--toc`)
- YAML frontmatter for Obsidian / Hugo (`--frontmatter`)
- Internal reasoning / thinking block rendering (`--include-thoughts`)
- Collapsible thinking blocks via `<details>` dropdowns (`--collapsible`)
- Per-turn metadata display: model, thinking level, tokens, timestamps (`--show-turn-metadata`)
- Token count and estimated API cost analytics (`--show-stats`)
- Mid-chat model and thinking level switch tracking
- Mid-chat system instruction revision tracking
- Generation interruption detection
- Multi-candidate draft branching support
- Inline media extraction to local files (`--extract-media`)
- Sensitivity redaction for API keys, emails, Drive IDs (`--anonymize`)
- Custom speaker labels (`--user-name`, `--assistant-name`)
- Batch directory processing (`--batch`)
- Grounding search query display with toggle (`--hide-search-queries`)
- Function call and function response formatting
- Code execution block rendering with output
- Google Drive attachment formatting
- Losing Heroine mode (`--losing-heroine`)
