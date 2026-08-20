#!/usr/bin/env python3
"""
gais2md - Convert Gemini AI Studio conversation exports (JSON) into clean, readable Markdown, HTML, and JSONL fine-tuning transcripts.

Features:
- HTML Export (--html generates a standalone dark/light mode HTML transcript)
- Fine-Tuning Exporter (--to-jsonl exports JSONL dataset for model training)
- Interactive Table of Contents (--toc)
- Multi-Candidate Draft Branching (Handles candidate variations)
- System Instruction Revision Tracking (Detects mid-chat prompt changes)
- Model & Thinking Level Switch Tracking (Per-message model changes)
- Interruption Detection (*[Generation interrupted by user]*)
- Run Settings (Model, Temp, Top-P, Top-K, Max Tokens, Safety, Tools)
- System Instructions
- Thoughts / Reasoning blocks (Optionally Collapsible via <details>)
- Custom Speaker Labels (--user-name, --assistant-name)
- Media Extraction (--extract-media saves base64 images to local files)
- Sensitivity Redaction (--anonymize masks API keys, emails, Drive IDs)
- YAML Frontmatter (--frontmatter for Obsidian / Hugo)
- Analytics & Cost Summaries (--show-stats)
- Batch Processing (--batch converts entire directories)
- Losing Heroine Flavor Mode (--losing-heroine)

Usage:
    Single File:
        gais2md input.json output.md [options]
        # or: python3 gais2md.py input.json output.md [options]

    HTML & JSONL Export:
        gais2md input.json output.md --html --to-jsonl

    Batch Mode:
        gais2md json_dir/ md_dir/ --batch [options]
"""

import argparse
import base64
import html
import json
import mimetypes
import random
import re
import sys
from datetime import datetime
from pathlib import Path

# --- Easter Egg Quotes (Makeine: Too Many Losing Heroines!) ---
LOSING_HEROINE_QUOTES = [
    "Nukumizu-kun. Girls can be divided into two categories: childhood friends or homewreckers.",
    "...It's not messed up. In fact, you should say my face is like rainbows.",
    "Nukumizu-kun, it's true that this box of <Fuwa Fuwa Soybean Mochi> is open. I'll admit that much, okay? Do you have any proof that I was the one who opened it? Or that I was the one who ate it?",
    "This is a mathematically proven proactive diet method. Maybe I should publish a book about it.",
    "Nukumizu-kun, dieting doesn't mean just starving yourself. Some say it's better to eat smaller portions more frequently, even if the daily calories are the same.",
    "Seaweed has low calories as well. From my perspective, it's pretty much zero.",
    "Nukumizu-kun, people can get burnt by a cold spoon if they believe it's hot enough. Kelp can be fried chicken if you believe hard enough.",
    "No, the bottom layer of this cookie tin is empty. Isn't that unfair?",
    "You're too naive, Nukumizu-kun. Valentine's Day isn't just for giving chocolates. It's for buying chocolates as well.",
    "The president is supposed to sacrifice everything for the sake of the Literature Club in exchange for his power. And since the president isn't here, the VP holds the highest authority.",
    "Alright, let's get started. First, we need to check out Nukumizu-kun's collection of unusual manga and light novels.",
    "He took my favorite piece of fried chicken from my bento without asking and ate it. In high school, doesn't that basically count as a proposal?",
    "Nukumizu-kun, love is like a game of musical chairs. But for some reason, my chair got yanked away before the music even started playing.",
    "I'm not eating right now because I'm hungry, Nukumizu-kun. I'm eating because my mouth feels lonely.",
    "Calories in sweet drinks don't really stick to your body because they're liquid. They just pass right through you, so practically speaking, it's zero.",
    "When I'm bored, I feel like I could eat these forever. I bought a dozen, but they probably won't last three days.",
    "It's fine. If worse comes to worst in the future, I'll just become a rich guy's second wife or something.",
    "Nukumizu-kun, don't look at me like I'm a stray dog you just fed a leftover sausage.",
    "Nukumizu-kun, do you even know what the original meaning of diet is? It originally meant 'daily meals'. So I've stopped getting caught up in temporary fluctuations in numbers.",
]


def get_losing_heroine_template(user_name: str = "User") -> dict:
    """Generate the Anna Yanami easter egg template data."""
    name = user_name.strip() if user_name and user_name != "User" else "Nukumizu"
    quotes = [q.replace("Nukumizu", name) for q in LOSING_HEROINE_QUOTES]
    return {
        "assistant_name": "Anna Yanami 🍱",
        "announcement": "'Calories consumed while processing transcripts don't count!' - 🦦",
        "header_html": (
            '<p align="center">\n'
            '  <i>"Calories consumed while converting transcripts don\'t count!"</i> — <b>Anna Yanami</b>\n'
            '</p>\n\n---\n\n'
        ),
        "quotes": quotes,
    }


def anonymize_text(text: str) -> str:
    """Redact sensitive patterns like Google API keys, emails, and Drive IDs."""
    if not text or not isinstance(text, str):
        return text
    text = re.sub(r"AIzaSy[A-Za-z0-9_-]{33}", "[REDACTED_API_KEY]", text)
    text = re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[REDACTED_EMAIL]", text
    )
    text = re.sub(r"(?<=id=)[a-zA-Z0-9_-]{28,35}", "[REDACTED_DRIVE_ID]", text)
    text = re.sub(r"(?<=/d/)[a-zA-Z0-9_-]{28,35}", "[REDACTED_DRIVE_ID]", text)
    return text


def slugify_heading(heading_text: str, anchor_counts: dict[str, int]) -> str:
    """Turn a Markdown heading into the same anchor GitHub/Obsidian would generate."""
    stripped = re.sub(r"[*_`]", "", heading_text)
    slug = re.sub(r"[^\w\- ]", "", stripped.lower()).strip()
    slug = re.sub(r"\s+", "-", slug)

    count = anchor_counts.get(slug, 0)
    anchor_counts[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def format_timestamp(iso_str: str | None) -> str | None:
    """Convert an ISO timestamp into a friendlier display format."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y at %H:%M UTC")
    except ValueError:
        return iso_str


def extract_system_instruction(data: dict, anonymize: bool = False) -> str | None:
    """Extract system instruction from string, object, or parts array format."""
    sys_inst = data.get("systemInstruction")
    if not sys_inst:
        return None

    result_text = None
    if isinstance(sys_inst, str):
        result_text = sys_inst.strip() or None
    elif isinstance(sys_inst, dict):
        parts = sys_inst.get("parts")
        if isinstance(parts, list):
            texts = []
            for part in parts:
                if isinstance(part, str) and part.strip():
                    texts.append(part.strip())
                elif isinstance(part, dict) and part.get("text"):
                    texts.append(part["text"].strip())
            if texts:
                result_text = "\n\n".join(texts)

        if not result_text:
            text = sys_inst.get("text")
            if isinstance(text, str) and text.strip():
                result_text = text.strip()

    if result_text and anonymize:
        result_text = anonymize_text(result_text)

    return result_text


def format_run_settings(data: dict) -> list[str]:
    """Format runSettings hyperparameters, tool toggles, and safety configuration."""
    run_settings = data.get("runSettings")
    if not isinstance(run_settings, dict) or not run_settings:
        return []

    lines = ["### Model & Run Settings", ""]

    model = run_settings.get("model")
    if model:
        clean_model = model.split("/")[-1]
        lines.append(f"- **Model:** `{clean_model}`")

    params = []
    if "temperature" in run_settings:
        params.append(f"Temperature: `{run_settings['temperature']}`")
    if "topP" in run_settings:
        params.append(f"Top-P: `{run_settings['topP']}`")
    if "topK" in run_settings:
        params.append(f"Top-K: `{run_settings['topK']}`")
    if "maxOutputTokens" in run_settings:
        params.append(f"Max Tokens: `{run_settings['maxOutputTokens']}`")
    if params:
        lines.append(f"- **Parameters:** {', '.join(params)}")

    if "stopSequences" in run_settings and run_settings["stopSequences"]:
        seqs = ", ".join(f"`{s}`" for s in run_settings["stopSequences"])
        lines.append(f"- **Stop Sequences:** {seqs}")

    if "responseMimeType" in run_settings:
        lines.append(f"- **Response Format:** `{run_settings['responseMimeType']}`")

    if "responseSchema" in run_settings and run_settings["responseSchema"]:
        schema_str = json.dumps(run_settings["responseSchema"], indent=2)
        lines.append("- **Response Schema:**")
        lines.append("```json")
        lines.append(schema_str)
        lines.append("```")

    tool_keys = {
        "enableCodeExecution": "Code Execution",
        "enableSearchAsATool": "Google Search Tool",
        "enableSearch": "Google Search",
        "enableBrowseAsATool": "Browse Tool",
        "enableAutoFunctionResponse": "Auto Function Response",
        "enableImageSearch": "Image Search",
        "enableGoogleMaps": "Google Maps",
        "enableGrounding": "Grounding",
    }
    enabled_tools = [
        name for key, name in tool_keys.items() if run_settings.get(key) is True
    ]
    if enabled_tools:
        lines.append(f"- **Enabled Tools:** {', '.join(enabled_tools)}")

    if "thinkingConfig" in run_settings:
        t_cfg = run_settings["thinkingConfig"]
        if isinstance(t_cfg, dict):
            t_items = [f"{k}: `{v}`" for k, v in t_cfg.items()]
            lines.append(f"- **Thinking Config:** {', '.join(t_items)}")
        else:
            lines.append(f"- **Thinking Config:** `{t_cfg}`")
    elif "thinkingLevel" in run_settings:
        lines.append(f"- **Thinking Level:** `{run_settings['thinkingLevel']}`")

    safety = run_settings.get("safetySettings")
    if isinstance(safety, list) and safety:
        lines.append("- **Safety Settings:**")
        for s in safety:
            if isinstance(s, dict):
                cat = s.get("category", "").replace("HARM_CATEGORY_", "").lower()
                thresh = s.get("threshold", "").replace("BLOCK_", "").lower()
                lines.append(f"  - `{cat}`: `{thresh}`")

    lines.append("")
    return lines


def extract_chunk_model_and_thinking(
    chunk: dict, current_model: str | None, current_thinking: str | None
) -> tuple[str | None, str | None]:
    """Extract model and thinking level for an individual chunk or turn."""
    chunk_model = chunk.get("model")
    if not chunk_model and isinstance(chunk.get("runSettings"), dict):
        chunk_model = chunk["runSettings"].get("model")

    clean_model = chunk_model.split("/")[-1] if chunk_model else current_model

    thinking = chunk.get("thinkingLevel")
    if thinking is None and isinstance(chunk.get("runSettings"), dict):
        thinking = chunk["runSettings"].get("thinkingLevel")

    if thinking is None:
        budget = chunk.get("thinkingBudget")
        if budget is None and isinstance(chunk.get("runSettings"), dict):
            budget = chunk["runSettings"].get("thinkingBudget")
        if budget is not None:
            thinking = f"Budget: {budget}"

    clean_thinking = str(thinking) if thinking is not None else current_thinking

    return clean_model, clean_thinking


def extract_inline_media(
    inline_data: dict, output_dir: Path, media_counter: int
) -> tuple[str | None, Path | None]:
    """Decode base64 inline media into a local file and return Markdown tag."""
    mime = inline_data.get("mimeType", "application/octet-stream")
    data_str = inline_data.get("data", "")
    if not data_str:
        return None, None

    try:
        raw_bytes = base64.b64decode(data_str)
    except Exception:
        return None, None

    ext = mimetypes.guess_extension(mime) or ".bin"
    if mime == "image/jpg":
        ext = ".jpg"

    media_dir = output_dir / "extracted_media"
    media_dir.mkdir(parents=True, exist_ok=True)

    filename = f"media_{media_counter:03d}{ext}"
    filepath = media_dir / filename
    filepath.write_bytes(raw_bytes)

    rel_path = f"extracted_media/{filename}"
    if mime.startswith("image/"):
        tag = f"![Extracted Image]({rel_path})"
    else:
        tag = f"[Extracted Media ({mime})]({rel_path})"

    return tag, filepath


def format_attachment(
    part: dict,
    extract_media: bool = False,
    output_dir: Path | None = None,
    media_counter_ref: list[int] | None = None,
    anonymize: bool = False,
) -> list[str]:
    """Format Google Drive attachments, inline media, or external file URIs."""
    lines = []

    for key, val in part.items():
        if key.startswith("drive") and isinstance(val, dict):
            doc_id = val.get("id", "unknown")
            if anonymize and len(doc_id) > 8:
                doc_id = f"{doc_id[:4]}...[REDACTED_DRIVE_ID]"
            title = val.get("title") or val.get("name")
            if title and anonymize:
                title = anonymize_text(title)
            mime = val.get("mimeType")

            raw_type = key[5:] if len(key) > 5 else "File"
            media_type = raw_type.capitalize() if raw_type else "File"

            info = []
            if title:
                info.append(f'"{title}"')
            info.append(f"ID: `{doc_id}`")
            if mime:
                info.append(f"Type: `{mime}`")

            lines.append(f"*[Attached {media_type} — {', '.join(info)}]*")

    inline_data = part.get("inlineData") or part.get("inline_data")
    if isinstance(inline_data, dict):
        if extract_media and output_dir and media_counter_ref is not None:
            media_counter_ref[0] += 1
            tag, _ = extract_inline_media(
                inline_data, output_dir, media_counter_ref[0]
            )
            if tag:
                lines.append(tag)
            else:
                mime = inline_data.get("mimeType", "unknown")
                lines.append(f"*[Inline Media — Type: `{mime}`]*")
        else:
            mime = inline_data.get("mimeType", "unknown")
            data_str = inline_data.get("data", "")
            size_info = f" ({len(data_str):,} base64 chars)" if data_str else ""
            lines.append(f"*[Inline Media — Type: `{mime}`{size_info}]*")

    file_data = part.get("fileData") or part.get("file_data")
    if isinstance(file_data, dict):
        uri = file_data.get("fileUri", "unknown")
        if anonymize:
            uri = anonymize_text(uri)
        mime = file_data.get("mimeType")
        mime_str = f", Type: `{mime}`" if mime else ""
        lines.append(f"*[File Reference — URI: `{uri}`{mime_str}]*")

    return lines


def format_tool_content(part: dict, anonymize: bool = False) -> list[str]:
    """Format code execution, function calls, and function responses."""
    lines = []

    exec_code = part.get("executableCode")
    if isinstance(exec_code, dict):
        lang = str(exec_code.get("language", "python")).lower()
        code = exec_code.get("code", "")
        if anonymize:
            code = anonymize_text(code)
        lines.append(f"```{lang}\n{code.rstrip()}\n```")

    exec_result = part.get("codeExecutionResult")
    if isinstance(exec_result, dict):
        outcome = exec_result.get("outcome", "OUTCOME_OK")
        output = exec_result.get("output", "").strip("\n")
        if anonymize:
            output = anonymize_text(output)
        status = "Output" if outcome in ("OUTCOME_OK", "OK") else f"Output ({outcome})"
        if output:
            lines.append(f"**{status}:**\n```text\n{output}\n```")
        else:
            lines.append(f"**{status}:** *(No output)*")

    func_call = part.get("functionCall") or part.get("call")
    if isinstance(func_call, dict):
        name = func_call.get("name", "unknown_function")
        args = func_call.get("args") or func_call.get("arguments") or {}
        call_id = func_call.get("id")
        id_str = f" (ID: `{call_id}`)" if call_id else ""
        args_json = json.dumps(args, indent=2)
        if anonymize:
            args_json = anonymize_text(args_json)
        lines.append(f"**Function Call:** `{name}`{id_str}\n```json\n{args_json}\n```")

    func_resp = part.get("functionResponse") or part.get("response")
    if isinstance(func_resp, dict):
        name = func_resp.get("name", "unknown_function")
        response = func_resp.get("response") or func_resp.get("content") or {}
        resp_id = func_resp.get("id")
        id_str = f" (ID: `{resp_id}`)" if resp_id else ""
        resp_json = json.dumps(response, indent=2)
        if anonymize:
            resp_json = anonymize_text(resp_json)
        lines.append(
            f"**Function Response:** `{name}`{id_str}\n```json\n{resp_json}\n```"
        )

    return lines


def format_grounding(
    data_item: dict,
    include_search_queries: bool = True,
    anonymize: bool = False,
) -> list[str]:
    """Format search queries and grounding source citations."""
    lines = []

    queries = data_item.get("webSearchQueries") or []
    grounding = data_item.get("groundingMetadata") or data_item.get("grounding")
    citations = data_item.get("citations")

    sources = []

    if isinstance(grounding, dict):
        if not queries:
            queries = grounding.get("webSearchQueries") or []

        g_chunks = (
            grounding.get("groundingChunks")
            or grounding.get("groundingSupports")
            or grounding.get("groundingSources")
        )
        if isinstance(g_chunks, list) and g_chunks:
            for item in g_chunks:
                if isinstance(item, dict):
                    web = item.get("web", {})
                    uri = web.get("uri") or item.get("uri")
                    ref = item.get("referenceNumber")
                    ref_str = f"[{ref}] " if ref else ""
                    title = web.get("title") or item.get("title") or uri
                    if uri:
                        if anonymize:
                            uri = anonymize_text(uri)
                            title = anonymize_text(title)
                        sources.append(f"{ref_str}[{title}]({uri})")

    if isinstance(citations, list) and citations:
        for cite in citations:
            if isinstance(cite, dict):
                uri = cite.get("uri")
                title = cite.get("title") or uri
                if uri:
                    if anonymize:
                        uri = anonymize_text(uri)
                        title = anonymize_text(title)
                    sources.append(f"[{title}]({uri})")

    if sources:
        lines.append(f"**Grounding Sources:** {', '.join(sources)}")

    if include_search_queries and queries and isinstance(queries, list):
        if anonymize:
            queries = [anonymize_text(q) for q in queries]
        query_list = ", ".join(f"`{q}`" for q in queries)
        lines.append(f"🔍 **Search Queries:** {query_list}")

    return lines


def is_chunk_interrupted(chunk: dict) -> bool:
    """Check if a model generation turn was interrupted or cut off mid-output."""
    role = chunk.get("role", "")
    if role not in ("model", "assistant"):
        return False

    if chunk.get("isThought") or chunk.get("thought"):
        return False

    for flag in (
        "interrupted",
        "isInterrupted",
        "userInterrupted",
        "cancelled",
        "isCancelled",
    ):
        if chunk.get(flag) is True:
            return True

    state = str(chunk.get("state", "")).upper()
    if state in ("INTERRUPTED", "CANCELLED", "USER_CANCELLED", "USER_CANCEL"):
        return True

    finish_reason = chunk.get("finishReason") or chunk.get("finish_reason")
    if finish_reason is not None:
        finish_str = str(finish_reason).upper()
        if finish_str in (
            "USER_CANCEL",
            "CANCELLED",
            "INTERRUPTED",
            "USER_INTERRUPT",
            "CLIENT_INTERRUPT",
        ):
            return True
        return False

    non_finish_bearing_keys = (
        "executableCode",
        "codeExecutionResult",
        "functionCall",
        "functionResponse",
    )
    if any(key in chunk for key in non_finish_bearing_keys):
        return False

    return True


def process_chunk(
    chunk: dict,
    include_thoughts: bool = False,
    include_search_queries: bool = True,
    collapsible: bool = False,
    extract_media: bool = False,
    output_dir: Path | None = None,
    media_counter_ref: list[int] | None = None,
    anonymize: bool = False,
) -> tuple[str | None, bool, bool]:
    """Process a chunk into a clean Markdown block."""
    is_thought = chunk.get("isThought", False)

    parts = chunk.get("parts")
    items_to_process = parts if (isinstance(parts, list) and parts) else [chunk]

    for item in items_to_process:
        if isinstance(item, dict) and (item.get("isThought") or item.get("thought")):
            is_thought = True
            break

    if is_thought and not include_thoughts:
        return None, True, True

    attachments = []
    tools = []
    grounding = format_grounding(chunk, include_search_queries, anonymize)

    for item in items_to_process:
        if isinstance(item, dict):
            attachments.extend(
                format_attachment(
                    item, extract_media, output_dir, media_counter_ref, anonymize
                )
            )
            tools.extend(format_tool_content(item, anonymize))
            if not grounding:
                grounding.extend(
                    format_grounding(item, include_search_queries, anonymize)
                )

    chunk_text = chunk.get("text")
    if isinstance(chunk_text, str) and chunk_text.strip():
        main_text = chunk_text.strip()
    else:
        text_pieces = []
        for item in items_to_process:
            if isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str) and t:
                    text_pieces.append(t)
        main_text = "".join(text_pieces).strip() if text_pieces else ""

    if main_text and anonymize:
        main_text = anonymize_text(main_text)

    blocks = []
    if attachments:
        blocks.append("\n\n".join(attachments))
    if main_text:
        blocks.append(main_text)
    if tools:
        blocks.append("\n\n".join(tools))
    if grounding:
        blocks.append("\n\n".join(grounding))

    if is_chunk_interrupted(chunk):
        blocks.append("*[Generation interrupted by user]*")

    if not blocks:
        return None, is_thought, False

    rendered = "\n\n".join(blocks)

    if is_thought:
        if collapsible:
            rendered = (
                "<details>\n"
                "<summary><b>Internal Reasoning</b></summary>\n\n"
                f"{rendered}\n\n"
                "</details>"
            )
        else:
            rendered = "\n".join(
                f"> {line}" if line else ">" for line in rendered.splitlines()
            )
        return rendered, True, False

    return rendered, False, False


def get_chunks(data: dict) -> list[dict]:
    """Extract conversation chunks from various Gemini JSON schema structures."""
    if "chunkedPrompt" in data and isinstance(data["chunkedPrompt"], dict):
        chunks = data["chunkedPrompt"].get("chunks")
        if isinstance(chunks, list):
            return chunks

    for fallback in ("contents", "prompts", "history"):
        if fallback in data and isinstance(data[fallback], list):
            return data[fallback]

    return []


def generate_yaml_frontmatter(data: dict, total_tokens: int) -> list[str]:
    """Generate YAML Frontmatter header block."""
    title = (
        data.get("title")
        or data.get("promptTitle")
        or data.get("name")
        or "Conversation Transcript"
    )
    model = data.get("runSettings", {}).get("model", "unknown").split("/")[-1]
    date_str = datetime.now().strftime("%Y-%m-%d")

    return [
        "---",
        f'title: "{title.strip()}"',
        f'model: "{model}"',
        f"date: {date_str}",
        "tags: [gais2md, ai-studio, gemini, transcript]",
        f"total_tokens: {total_tokens}",
        "---",
        "",
    ]


def generate_summary_stats(
    chunk_count: int, total_tokens: int, interrupted_count: int
) -> list[str]:
    """Generate a summary and analytics section at the end of transcript."""
    lines = ["## Conversation Summary & Analytics", ""]
    lines.append(f"- **Total Message Turns:** {chunk_count:,}")
    lines.append(f"- **Total Recorded Tokens:** {total_tokens:,}")
    if interrupted_count:
        lines.append(f"- **Interrupted Turns:** {interrupted_count}")

    if total_tokens > 0:
        est_cost = (total_tokens / 1_000_000) * 0.15
        lines.append(f"- **Estimated API Cost:** ~${est_cost:.4f} USD")

    lines.append("")
    return lines


def export_to_jsonl(data: dict, anonymize: bool = False) -> str:
    """Export conversation history into OpenAI / Gemini fine-tuning JSONL format."""
    chunks = get_chunks(data)
    messages = []

    sys_inst = extract_system_instruction(data, anonymize=anonymize)
    if sys_inst:
        messages.append({"role": "system", "content": sys_inst})

    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        if chunk.get("isThought"):
            continue

        role = chunk.get("role", "user")
        if role in ("model", "assistant"):
            role = "assistant"
        elif role != "system":
            role = "user"

        text_pieces = []
        text = chunk.get("text")
        if text:
            text_pieces.append(text)

        parts = chunk.get("parts", [])
        for p in parts:
            if not isinstance(p, dict) or p.get("isThought") or p.get("thought"):
                continue
            if p.get("text"):
                text_pieces.append(p["text"])
            if p.get("executableCode"):
                code = p["executableCode"].get("code", "")
                text_pieces.append(f"```python\n{code}\n```")
            if p.get("codeExecutionResult"):
                out = p["codeExecutionResult"].get("output", "")
                text_pieces.append(f"Output:\n```text\n{out}\n```")
            if p.get("functionCall"):
                fc = p["functionCall"]
                text_pieces.append(f"Call: {fc.get('name')}({json.dumps(fc.get('args', {}))})")
            if p.get("functionResponse"):
                fr = p["functionResponse"]
                text_pieces.append(f"Response: {json.dumps(fr.get('response', {}))}")

        full_text = "\n\n".join(text_pieces).strip()
        if full_text:
            if anonymize:
                full_text = anonymize_text(full_text)
            messages.append({"role": role, "content": full_text})

    return json.dumps({"messages": messages}, ensure_ascii=False) + "\n"


def convert_md_to_html(md_text: str, title: str) -> str:
    """Convert Markdown transcript into a styled, standalone HTML document."""
    escaped_title = html.escape(title)
    html_body = md_text

    # Protect code blocks with placeholders before splitting paragraphs
    code_blocks = []
    def code_block_sub(m):
        lang = m.group(1)
        code = html.escape(m.group(2))
        placeholder = f"___CODE_BLOCK_{len(code_blocks)}___"
        code_blocks.append(f'<pre><code class="language-{lang}">{code}</code></pre>')
        return placeholder

    html_body = re.sub(r"```([a-zA-Z0-9_-]*)\n(.*?)```", code_block_sub, html_body, flags=re.DOTALL)

    # Inline code
    html_body = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", html_body)

    # Headers with anchors
    anchor_counts: dict[str, int] = {}
    def header_sub(m):
        level = len(m.group(1))
        text = m.group(2).strip()
        slug = slugify_heading(text, anchor_counts)
        return f'<h{level} id="{slug}">{text}</h{level}>'

    html_body = re.sub(r"^(#{1,6})\s+(.+)$", header_sub, html_body, flags=re.MULTILINE)

    # Bold and Italic
    html_body = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", html_body)
    html_body = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html_body)

    # Split paragraphs
    paragraphs = html_body.split("\n\n")
    formatted_paras = []
    for p in paragraphs:
        p_str = p.strip()
        if not p_str:
            continue
        if p_str.startswith(("___CODE_BLOCK_", "<h", "<pre", "<details", "<ul", "<ol", "---", "<blockquote")):
            formatted_paras.append(p_str)
        else:
            formatted_paras.append(f"<p>{p_str.replace(chr(10), '<br>')}</p>")

    html_content = "\n\n".join(formatted_paras)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        html_content = html_content.replace(f"___CODE_BLOCK_{i}___", block)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escaped_title}</title>
<style>
:root {{
  --bg-color: #ffffff;
  --text-color: #1f2328;
  --card-bg: #f6f8fa;
  --border-color: #d0d7de;
  --code-bg: #eff1f3;
  --link-color: #0969da;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg-color: #0d1117;
    --text-color: #e6edf3;
    --card-bg: #161b22;
    --border-color: #30363d;
    --code-bg: #1f242c;
    --link-color: #2f81f7;
  }}
}}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
  max-width: 880px;
  margin: 0 auto;
  padding: 2rem 1rem;
  background-color: var(--bg-color);
  color: var(--text-color);
}}
h1, h2, h3, h4 {{
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 0.3em;
  margin-top: 1.5em;
}}
pre {{
  background-color: var(--code-bg);
  padding: 1rem;
  border-radius: 6px;
  overflow-x: auto;
  border: 1px solid var(--border-color);
}}
code {{
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
  font-size: 85%;
  background-color: var(--code-bg);
  padding: 0.2em 0.4em;
  border-radius: 3px;
}}
pre code {{
  padding: 0;
  background-color: transparent;
}}
blockquote {{
  margin: 0;
  padding: 0 1em;
  color: #656d76;
  border-left: 0.25em solid var(--border-color);
}}
details {{
  background-color: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 0.5rem 1rem;
  margin: 1rem 0;
}}
summary {{
  cursor: pointer;
  font-weight: 600;
}}
a {{
  color: var(--link-color);
  text-decoration: none;
}}
a:hover {{
  text-decoration: underline;
}}
hr {{
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: var(--border-color);
  border: 0;
}}
</style>
</head>
<body>
{html_content}
</body>
</html>"""


def convert(
    data: dict | list,
    include_thoughts: bool = False,
    show_turn_metadata: bool = False,
    include_search_queries: bool = True,
    collapsible_thoughts: bool = False,
    extract_media: bool = False,
    output_path: Path | None = None,
    user_name: str = "User",
    assistant_name: str = "Assistant",
    frontmatter: bool = False,
    show_stats: bool = False,
    anonymize: bool = False,
    include_toc: bool = False,
    alt_template: dict | None = None,
) -> str:
    """Convert parsed AI Studio JSON data into Markdown string format."""
    if isinstance(data, list):
        if not data:
            return "# Conversation Transcript\n\n*(Empty Export)*\n"
        data = data[0]

    if not isinstance(data, dict):
        return "# Conversation Transcript\n\n*(Invalid JSON Structure)*\n"

    lines = []
    chunks = get_chunks(data)
    alt_quotes = alt_template.get("quotes", []) if alt_template else []

    total_tokens = 0
    interrupted_count = 0
    for chunk in chunks:
        if isinstance(chunk, dict):
            if chunk.get("tokenCount"):
                total_tokens += chunk["tokenCount"]
            if is_chunk_interrupted(chunk):
                interrupted_count += 1

    if frontmatter:
        lines.extend(generate_yaml_frontmatter(data, total_tokens))

    title = (
        data.get("title")
        or data.get("promptTitle")
        or data.get("name")
        or "Conversation Transcript"
    )
    if anonymize:
        title = anonymize_text(title)
    lines.append(f"# {title.strip()}")
    lines.append("")

    settings_lines = format_run_settings(data)
    if settings_lines:
        lines.extend(settings_lines)

    sys_inst = extract_system_instruction(data, anonymize=anonymize)
    if sys_inst:
        quoted_sys = "\n".join(
            f"> {line}" if line else ">" for line in sys_inst.splitlines()
        )
        lines.extend(["## System Instruction", "", quoted_sys, ""])

    lines.extend(["---", ""])
    toc_insertion_index = len(lines)

    role_labels = {
        "user": user_name,
        "model": assistant_name,
        "assistant": assistant_name,
        "system": "System",
        "function": "Tool",
        "tool": "Tool",
    }

    last_speaker_key = None
    skipped = 0
    media_counter = [0]
    turn_counter = 0
    toc_entries = []
    anchor_counts: dict[str, int] = {}
    output_dir = output_path.parent if output_path else Path(".")

    run_settings = data.get("runSettings", {})
    init_model = run_settings.get("model", "").split("/")[-1] or None
    init_thinking = run_settings.get("thinkingLevel") or (
        f"Budget: {run_settings['thinkingBudget']}"
        if "thinkingBudget" in run_settings
        else None
    )

    current_model = init_model
    current_thinking = str(init_thinking) if init_thinking is not None else None
    current_sys_inst = sys_inst

    for chunk in chunks:
        if not isinstance(chunk, dict):
            skipped += 1
            continue

        role = chunk.get("role", "unknown")
        label = role_labels.get(role, role.capitalize())

        chunk_sys = extract_system_instruction(chunk, anonymize=anonymize)
        if chunk_sys and chunk_sys != current_sys_inst:
            lines.append("🔄 *[System Instruction Updated]*")
            lines.append(
                "\n".join(
                    f"> {line}" if line else ">" for line in chunk_sys.splitlines()
                )
            )
            lines.append("")
            current_sys_inst = chunk_sys

        chunk_model, chunk_thinking = extract_chunk_model_and_thinking(
            chunk, current_model, current_thinking
        )

        model_switched = (
            chunk_model and current_model and chunk_model != current_model
        )
        thinking_switched = (
            chunk_thinking
            and current_thinking
            and chunk_thinking != current_thinking
        )

        if model_switched or thinking_switched:
            switch_info = []
            if model_switched:
                switch_info.append(f"Model switched to `{chunk_model}`")
                current_model = chunk_model
            if thinking_switched:
                switch_info.append(f"Thinking: `{chunk_thinking}`")
                current_thinking = chunk_thinking

            lines.append(f"🔄 *[{' | '.join(switch_info)}]*")
            lines.append("")

        candidates = chunk.get("candidates")
        chunks_to_process = (
            candidates
            if (isinstance(candidates, list) and len(candidates) > 1)
            else [chunk]
        )

        for cand_idx, item_chunk in enumerate(chunks_to_process, 1):
            cand_prefix = (
                f" (Candidate {cand_idx})" if len(chunks_to_process) > 1 else ""
            )

            rendered, turn_is_thought, was_filtered = process_chunk(
                chunk=item_chunk,
                include_thoughts=include_thoughts,
                include_search_queries=include_search_queries,
                collapsible=collapsible_thoughts,
                extract_media=extract_media,
                output_dir=output_dir,
                media_counter_ref=media_counter,
                anonymize=anonymize,
            )

            if not rendered:
                if not was_filtered:
                    skipped += 1
                continue

            if alt_quotes and role in ("model", "assistant") and not turn_is_thought:
                rendered = random.choice(alt_quotes)

            speaker_key = (role, turn_is_thought, cand_idx)
            if speaker_key != last_speaker_key:
                header_suffix = " *(internal reasoning)*" if turn_is_thought else ""

                meta_details = []
                if show_turn_metadata:
                    if chunk_model:
                        meta_details.append(chunk_model)
                    if chunk_thinking:
                        meta_details.append(f"thinking: {chunk_thinking}")
                    token_count = item_chunk.get("tokenCount")
                    if token_count is not None:
                        meta_details.append(f"{token_count:,} tokens")
                    finish_reason = item_chunk.get("finishReason")
                    if finish_reason and finish_reason.upper() != "STOP":
                        meta_details.append(f"finish: {finish_reason}")
                    created_time = format_timestamp(
                        item_chunk.get("createTime") or item_chunk.get("timestamp")
                    )
                    if created_time:
                        meta_details.append(created_time)

                meta_suffix = f" *({', '.join(meta_details)})*" if meta_details else ""

                turn_counter += 1
                header_title = f"{label}{cand_prefix}"
                lines.append(f"## {header_title}{header_suffix}{meta_suffix}")
                lines.append("")

                full_heading_text = f"{header_title}{header_suffix}{meta_suffix}"
                anchor = slugify_heading(full_heading_text, anchor_counts)
                toc_entries.append(
                    f"- [{turn_counter}. {header_title}](#{anchor})"
                )

                last_speaker_key = speaker_key

            lines.append(rendered)
            lines.append("")

    citations = data.get("citations")
    if isinstance(citations, list) and citations:
        lines.extend(["## Top-Level Citations", ""])
        for cite in citations:
            if isinstance(cite, dict):
                uri = cite.get("uri")
                c_title = cite.get("title") or uri
                if uri:
                    if anonymize:
                        uri = anonymize_text(uri)
                        c_title = anonymize_text(c_title)
                    lines.append(f"- [{c_title}]({uri})")
            elif isinstance(cite, str):
                c_str = anonymize_text(cite) if anonymize else cite
                lines.append(f"- <{c_str}>")
        lines.append("")

    pending = data.get("chunkedPrompt", {}).get("pendingInputs")
    valid_pending = []
    if isinstance(pending, list):
        for item in pending:
            if isinstance(item, dict):
                p_text = item.get("text", "").strip()
                if p_text:
                    valid_pending.append(
                        anonymize_text(p_text) if anonymize else p_text
                    )
            elif isinstance(item, str) and item.strip():
                valid_pending.append(
                    anonymize_text(item.strip()) if anonymize else item.strip()
                )

    if valid_pending:
        lines.extend(["## Pending Draft Inputs", ""])
        for draft in valid_pending:
            lines.append(f"*(User draft)*: {draft}")
            lines.append("")

    if skipped:
        lines.append(f"*[{skipped} chunk(s) omitted — empty or unrecognized content]*")
        lines.append("")

    if show_stats:
        lines.extend(
            generate_summary_stats(len(chunks), total_tokens, interrupted_count)
        )

    if include_toc and toc_entries:
        toc_lines = ["## Table of Contents", ""] + toc_entries + ["", "---", ""]
        lines = (
            lines[:toc_insertion_index]
            + toc_lines
            + lines[toc_insertion_index:]
        )

    return "\n".join(lines).rstrip() + "\n"


def process_file(
    input_file: Path, output_file: Path, args: argparse.Namespace
) -> None:
    """Process a single JSON file into Markdown, HTML, or JSONL."""
    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"Error parsing JSON file '{input_file}': {e}")
    except OSError as e:
        sys.exit(f"Error reading file '{input_file}': {e}")

    if args.anonymize:
        print(
            "Notice: --anonymize uses regex heuristics (API keys, emails, Drive IDs). "
            "Please review the output transcript before publishing sensitive data."
        )

    alt_template = get_losing_heroine_template(args.user_name) if getattr(args, "losing_heroine", False) else {}

    if alt_template:
        args.assistant_name = alt_template.get("assistant_name", args.assistant_name)
        announcement = alt_template.get("announcement")
        if announcement:
            print(announcement)

    markdown = convert(
        data=data,
        include_thoughts=args.include_thoughts,
        show_turn_metadata=args.show_turn_metadata,
        include_search_queries=not args.hide_search_queries,
        collapsible_thoughts=args.collapsible,
        extract_media=args.extract_media,
        output_path=output_file,
        user_name=args.user_name,
        assistant_name=args.assistant_name,
        frontmatter=args.frontmatter,
        show_stats=args.show_stats,
        anonymize=args.anonymize,
        include_toc=args.toc,
        alt_template=alt_template,
    )

    if alt_template and "header_html" in alt_template:
        header_html = alt_template["header_html"]
        if args.frontmatter and markdown.startswith("---"):
            parts = markdown.split("---\n", 2)
            if len(parts) >= 3:
                markdown = f"---{parts[1]}---\n\n{header_html}{parts[2]}"
            else:
                markdown = header_html + markdown
        else:
            markdown = header_html + markdown

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(markdown, encoding="utf-8")
        print(f"Wrote {len(markdown):,} characters to '{output_file}'")
    except OSError as e:
        sys.exit(f"Error writing Markdown file '{output_file}': {e}")

    if args.html:
        html_path = output_file.with_suffix(".html")
        title = (
            data.get("title")
            or data.get("promptTitle")
            or data.get("name")
            or "Conversation Transcript"
        )
        html_content = convert_md_to_html(markdown, title)
        try:
            html_path.write_text(html_content, encoding="utf-8")
            print(f"Wrote HTML transcript to '{html_path}'")
        except OSError as e:
            sys.exit(f"Error writing HTML file '{html_path}': {e}")

    if args.to_jsonl:
        jsonl_path = output_file.with_suffix(".jsonl")
        jsonl_content = export_to_jsonl(data, anonymize=args.anonymize)
        try:
            jsonl_path.write_text(jsonl_content, encoding="utf-8")
            print(f"Wrote JSONL fine-tuning dataset to '{jsonl_path}'")
        except OSError as e:
            sys.exit(f"Error writing JSONL file '{jsonl_path}': {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gais2md",
        description="gais2md: Convert Gemini AI Studio JSON export(s) to Markdown, HTML, and JSONL.",
    )
    parser.add_argument(
        "input", type=Path, help="Path to input JSON file (or directory if --batch)"
    )
    parser.add_argument(
        "output", type=Path, help="Path to output Markdown file (or directory if --batch)"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch process all .json files in input directory to output directory",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate a self-contained styled HTML transcript file",
    )
    parser.add_argument(
        "--to-jsonl",
        action="store_true",
        help="Export conversation to JSONL fine-tuning dataset format",
    )
    parser.add_argument(
        "--toc",
        action="store_true",
        help="Include a jump-link Table of Contents at the top",
    )
    parser.add_argument(
        "--include-thoughts",
        action="store_true",
        help="Include model internal reasoning/thinking chunks",
    )
    parser.add_argument(
        "--collapsible",
        action="store_true",
        help="Wrap thinking blocks inside HTML <details> dropdowns",
    )
    parser.add_argument(
        "--extract-media",
        action="store_true",
        help="Decode inline base64 images/media to files and embed links",
    )
    parser.add_argument(
        "--frontmatter",
        action="store_true",
        help="Generate YAML frontmatter header (for Obsidian/Hugo)",
    )
    parser.add_argument(
        "--show-stats",
        action="store_true",
        help="Append token count & estimated API cost analytics section",
    )
    parser.add_argument(
        "--anonymize",
        action="store_true",
        help=(
            "Mask API keys, emails, and Drive IDs using pattern heuristics. "
            "Note: Heuristic-based; manual review recommended for sensitive transcripts."
        ),
    )
    parser.add_argument(
        "--show-turn-metadata",
        action="store_true",
        help="Include turn-level metadata (model, thinking level, token count, finish reason, timestamps)",
    )
    parser.add_argument(
        "--hide-search-queries",
        action="store_true",
        help="Hide raw internal grounding search queries",
    )
    parser.add_argument(
        "--user-name",
        type=str,
        default="User",
        help="Custom header label for User (default: 'User')",
    )
    parser.add_argument(
        "--assistant-name",
        type=str,
        default="Assistant",
        help="Custom header label for Assistant (default: 'Assistant')",
    )
    parser.add_argument(
        "--losing-heroine",
        action="store_true",
        help="Easter egg: theme assistant responses with Anna Yanami quotes (Makeine)",
    )

    args = parser.parse_args()

    if args.batch:
        if not args.input.is_dir():
            sys.exit(f"Error: Input path '{args.input}' must be a directory when using --batch.")
        json_files = [
            f for f in args.input.iterdir()
            if f.is_file() and f.suffix.lower() in ("", ".json")
        ]
        if not json_files:
            sys.exit(f"Error: No valid JSON or extensionless files found in '{args.input}'.")

        print(f"Batch processing {len(json_files)} JSON file(s)...")
        for json_file in json_files:
            out_file = args.output / f"{json_file.stem}.md"
            process_file(json_file, out_file, args)
    else:
        if not args.input.is_file():
            sys.exit(f"Error: Input file '{args.input}' does not exist.")
        process_file(args.input, args.output, args)


if __name__ == "__main__":
    main()
