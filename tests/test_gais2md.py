import json
import tempfile
import unittest
from pathlib import Path

import gais2md


class TestGais2MD(unittest.TestCase):
    def setUp(self):
        self.sample_data = {
            "title": "Edge Case Transcript",
            "runSettings": {
                "model": "models/gemini-1.5-pro",
                "temperature": 0.7,
                "thinkingLevel": "HIGH",
            },
            "systemInstruction": {
                "parts": [{"text": "You are a helpful test assistant."}]
            },
            "chunkedPrompt": {
                "chunks": [
                    {
                        "role": "user",
                        "text": "Write code for Fibonacci.",
                        "createTime": "2026-08-20T10:00:00Z",
                    },
                    {
                        "role": "model",
                        "isThought": True,
                        "text": "Internal reasoning step.",
                    },
                    {
                        "role": "model",
                        "model": "models/gemini-1.5-pro",
                        "parts": [
                            {
                                "executableCode": {
                                    "language": "PYTHON",
                                    "code": "def fib(n):\n\n    return n\n",
                                }
                            },
                            {
                                "codeExecutionResult": {
                                    "outcome": "OUTCOME_OK",
                                    "output": "55\n",
                                }
                            },
                        ],
                        "isInterrupted": True,
                    },
                    {
                        "role": "user",
                        "text": "Switch model.",
                    },
                    {
                        "role": "model",
                        "model": "models/gemini-1.5-flash",
                        "text": "Summary output.",
                    },
                ]
            },
        }

    def test_markdown_conversion(self):
        md = gais2md.convert(
            self.sample_data,
            include_thoughts=True,
            include_toc=True,
            frontmatter=True,
        )

        self.assertTrue(md.startswith("---"))
        self.assertIn("## Table of Contents", md)

        frontmatter_end = md.find("---\n\n# ")
        toc_pos = md.find("## Table of Contents")
        self.assertGreater(toc_pos, frontmatter_end)

        self.assertIn("*[Generation interrupted by user]*", md)
        self.assertIn("Model switched to `gemini-1.5-flash`", md)

    def test_html_conversion(self):
        md = gais2md.convert(self.sample_data, include_thoughts=True)
        html = gais2md.convert_md_to_html(md, "Edge Case Transcript")

        self.assertNotIn("<p>    return n", html)
        self.assertIn("<code class=\"language-python\">def fib(n):\n\n    return n\n</code>", html)

    def test_jsonl_export(self):
        jsonl = gais2md.export_to_jsonl(self.sample_data)
        parsed = json.loads(jsonl)

        messages = parsed.get("messages", [])
        self.assertEqual(messages[0]["role"], "system")

        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        self.assertTrue(any("def fib" in m["content"] for m in assistant_msgs))

    def test_anonymization(self):
        text = "Key: AIzaSy123456789012345678901234567890123, Email: test@example.com"
        redacted = gais2md.anonymize_text(text)

        self.assertNotIn("AIzaSy123456789012345678901234567890123", redacted)
        self.assertNotIn("test@example.com", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)

    def test_cli_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.json"
            output_path = Path(tmpdir) / "output.md"

            input_path.write_text(json.dumps(self.sample_data), encoding="utf-8")

            args = gais2md.argparse.Namespace(
                input=input_path,
                output=output_path,
                batch=False,
                html=True,
                to_jsonl=True,
                toc=True,
                include_thoughts=True,
                collapsible=False,
                extract_media=False,
                frontmatter=True,
                show_stats=True,
                anonymize=False,
                show_turn_metadata=True,
                hide_search_queries=False,
                user_name="User",
                assistant_name="Assistant",
                losing_heroine=False,
            )

            gais2md.process_file(input_path, output_path, args)

            self.assertTrue(output_path.exists())
            self.assertTrue(output_path.with_suffix(".html").exists())
            self.assertTrue(output_path.with_suffix(".jsonl").exists())

    def test_extensionless_file_conversion(self):
        extensionless_file = Path(__file__).parent / "Evaluating Your Portfolio Project"
        if extensionless_file.exists():
            data = json.loads(extensionless_file.read_text(encoding="utf-8"))
            md = gais2md.convert(data, include_thoughts=True)
            self.assertIn("gemini-3.7-flash", md)


if __name__ == "__main__":
    unittest.main()
