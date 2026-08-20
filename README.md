# gais2md

Convert [Google AI Studio](https://aistudio.google.com/) conversation exports (JSON) into clean, readable **Markdown**, **HTML**, and **JSONL** fine-tuning transcripts.

## Features

| Feature | Flag |
|---|---|
| Standalone dark/light HTML transcript | `--html` |
| JSONL fine-tuning dataset export | `--to-jsonl` |
| Jump-link Table of Contents | `--toc` |
| YAML frontmatter (Obsidian / Hugo) | `--frontmatter` |
| Internal reasoning / thinking blocks | `--include-thoughts` |
| Collapsible `<details>` thought dropdowns | `--collapsible` |
| Per-turn metadata (model, tokens, timestamps) | `--show-turn-metadata` |
| Token count & estimated API cost analytics | `--show-stats` |
| Inline media extraction to local files | `--extract-media` |
| Sensitivity redaction (API keys, emails, Drive IDs) | `--anonymize` |
| Custom speaker labels | `--user-name` / `--assistant-name` |
| Batch directory processing | `--batch` |

**Automatically detected** (no flags needed):
- Mid-chat model & thinking level switches
- System instruction revisions
- Generation interruptions
- Multi-candidate draft branches
- Code execution blocks & function calls
- Google Search grounding with source citations
- Google Drive attachments

## Requirements

- Python **3.10+**
- No external dependencies — stdlib only

## Installation

### Direct usage (no install)

```bash
python3 gais2md.py input.json output.md
```

### Install as CLI tool

```bash
pip install .
gais2md input.json output.md
```

## Usage

### Basic conversion

```bash
gais2md input.json output.md
```

### Full-featured export

```bash
gais2md input.json output.md \
  --html \
  --to-jsonl \
  --toc \
  --frontmatter \
  --include-thoughts \
  --collapsible \
  --show-turn-metadata \
  --show-stats
```

### Batch processing

```bash
gais2md json_folder/ output_folder/ --batch --html
```

### Privacy-safe export

```bash
gais2md input.json output.md --anonymize
```

### Custom speaker names

```bash
gais2md input.json output.md --user-name "Alice" --assistant-name "Gemini"
```

## How to find your JSON files

Google AI Studio automatically saves your prompts and conversation histories to **Google Drive**.

1. Go to your [Google Drive](https://drive.google.com/).
2. Open the **"AI Studio"** folder created by Google.
3. Download your conversation file to your computer.
4. Run `gais2md` on the downloaded file in the same directory:

```bash
gais2md "Conversation Name" output.md
```

## Output formats

| Format | Description |
|---|---|
| `.md` | Clean Markdown transcript (always generated) |
| `.html` | Self-contained styled HTML with dark/light mode (`--html`) |
| `.jsonl` | OpenAI-compatible fine-tuning dataset (`--to-jsonl`) |

## All options

```
usage: gais2md [-h] [--batch] [--html] [--to-jsonl] [--toc]
               [--include-thoughts] [--collapsible] [--extract-media]
               [--frontmatter] [--show-stats] [--anonymize]
               [--show-turn-metadata] [--hide-search-queries]
               [--user-name USER_NAME] [--assistant-name ASSISTANT_NAME]
               [--losing-heroine]
               input output
```

Run `gais2md --help` for full descriptions.

## Running tests

```bash
python3 -m unittest discover tests
```

This creates synthetic edge-case JSON data and validates Markdown, HTML, and JSONL output correctness.

## License

[MIT](LICENSE) © Iskender Usenbekov
