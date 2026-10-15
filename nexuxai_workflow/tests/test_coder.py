
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import coder
from services import llm
from services.llm import LLMError
from tests.helpers import (
    ScriptedChat,
    make_response,
    make_tool_call,
)


# The current app is frontend-only.
# README.md is created by the coder's infrastructure setup.
# .gitignore is platform-managed and must not be written by the model.
GOOD_FILES = {
    "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Application</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <main>
        <h1>Test Application</h1>
        <button id="test-button">Click me</button>
        <p id="message">Ready</p>
    </main>
    <script src="script.js"></script>
</body>
</html>
""",
    "style.css": """body {
    font-family: Arial, sans-serif;
    margin: 2rem;
}

button {
    padding: 0.5rem 1rem;
}
""",
    "script.js": """const button = document.getElementById("test-button");
const message = document.getElementById("message");

if (button && message) {
    button.addEventListener("click", () => {
        message.textContent = "Button clicked";
    });
}
""",
}


def writes(*names, start=1, sig=None):
    """Create tool calls for the specified model-generated files."""
    return [
        make_tool_call(
            f"call_{start + i}",
            "write_file",
            {"path": name, "content": GOOD_FILES[name]},
            signature=sig if i == 0 else None,
        )
        for i, name in enumerate(names)
    ]


def all_frontend_writes(start=1, sig=None):
    return writes("index.html", "style.css", "script.js", start=start, sig=sig)


class CoderBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        patcher = mock.patch.object(
            coder, "GENERATED_DIR", Path(self.tmp.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.pdir = Path(self.tmp.name) / "proj_1"

    def run_agent(self, script, **state):
        chat = ScriptedChat(script)

        with mock.patch.object(llm, "chat", chat):
            result = coder.coder_agent(
                {
                    "project_id": "proj_1",
                    "user_request": "Build a frontend test application",
                    **state,
                }
            )

        return result, chat


class Generation(CoderBase):
    def test_happy_path_multi_round_and_parallel_calls(self):
        script = [
            make_response(
                calls=writes(
                    "index.html",
                    "style.css",
                    start=1,
                    sig="SIG123",
                )
            ),
            make_response(calls=writes("script.js", start=3)),
        ]

        result, chat = self.run_agent(script)

        self.assertEqual(result["coder_status"], "COMPLETED")
        self.assertEqual(result["coder_missing_files"], [])

        for name in coder.REQUIRED_FILES:
            self.assertTrue((self.pdir / name).is_file(), name)

        # Check that the next request contains the previous tool results.
        second = chat.requests[1]
        assistant = [
            message
            for message in second
            if message["role"] == "assistant"
        ][0]

        self.assertEqual(
            assistant["tool_calls"][0]["extra_content"]["google"][
                "thought_signature"
            ],
            "SIG123",
        )
        self.assertNotIn("annotations", assistant)

        tool_messages = [
            message for message in second if message["role"] == "tool"
        ]
        self.assertEqual(
            [message["tool_call_id"] for message in tool_messages],
            ["call_1", "call_2"],
        )
        self.assertTrue(
            all(
                json.loads(message["content"])["ok"]
                for message in tool_messages
            )
        )
        self.assertEqual(tool_messages[0]["name"], "write_file")

    def test_spec_and_project_context_reach_the_model(self):
        script = [make_response(calls=all_frontend_writes())]

        _, chat = self.run_agent(
            script,
            developer_output="SPEC-MARKER-ABC",
            plan="PLAN-MARKER",
            research_output="RESEARCH-MARKER",
            project_context="CONTEXT-MARKER",
        )

        prompt = chat.requests[0][1]["content"]

        self.assertIn("SPEC-MARKER-ABC", prompt)
        self.assertIn("CONTEXT-MARKER", prompt)
        self.assertNotIn("PLAN-MARKER", prompt)

    def test_falls_back_to_plan_and_research_without_spec(self):
        script = [make_response(calls=all_frontend_writes())]

        _, chat = self.run_agent(
            script,
            plan="PLAN-MARKER",
            research_output="RESEARCH-MARKER",
        )

        prompt = chat.requests[0][1]["content"]

        self.assertIn("PLAN-MARKER", prompt)
        self.assertIn("RESEARCH-MARKER", prompt)

    def test_platform_creates_infrastructure_files(self):
        result, _ = self.run_agent(
            [make_response(calls=all_frontend_writes())]
        )

        self.assertEqual(result["coder_status"], "COMPLETED")
        self.assertTrue((self.pdir / "README.md").is_file())
        self.assertTrue((self.pdir / ".gitignore").is_file())

    def test_platform_managed_gitignore_cannot_be_overwritten(self):
        evil = make_tool_call(
            "evil",
            "write_file",
            {"path": ".gitignore", "content": "unsafe"},
        )

        # The valid source files are still generated after the rejected call.
        calls = [evil] + all_frontend_writes(start=2)
        result, _ = self.run_agent([make_response(calls=calls)])

        self.assertEqual(result["coder_status"], "COMPLETED")

        out = coder.execute_tool_call(self.pdir, evil, {})
        self.assertFalse(out["ok"])
        self.assertIn("managed by the platform", out["error"])

    def test_malformed_arguments_are_reported_and_recovered(self):
        bad = make_tool_call(
            "bad",
            "write_file",
            None,
            raw_arguments='{"path": "index.html", "content": "broken',
        )

        script = [
            make_response(calls=[bad], finish="length"),
            make_response(calls=all_frontend_writes(start=2)),
        ]

        result, chat = self.run_agent(script)

        self.assertEqual(result["coder_status"], "COMPLETED")

        tool_messages = [
            message
            for message in chat.requests[1]
            if message["role"] == "tool"
        ]
        self.assertTrue(tool_messages)

        output = json.loads(tool_messages[0]["content"])
        self.assertFalse(output["ok"])
        self.assertIn("not valid JSON", output["error"])

    def test_python_syntax_validation_does_not_break_frontend_generation(self):
        # The current coder validates Python files, not JavaScript syntax.
        # A normal frontend-only project should complete successfully.
        result, _ = self.run_agent(
            [make_response(calls=all_frontend_writes())]
        )

        self.assertEqual(result["coder_status"], "COMPLETED")

    def test_path_traversal_env_and_unknown_tool_are_rejected(self):
        calls = [
            make_tool_call(
                "a",
                "write_file",
                {"path": "../escape.py", "content": "x = 1"},
            ),
            make_tool_call(
                "b",
                "write_file",
                {"path": "C:/Windows/x.py", "content": "x = 1"},
            ),
            make_tool_call(
                "c",
                "write_file",
                {"path": ".env", "content": "KEY=1"},
            ),
            make_tool_call(
                "d",
                "delete_file",
                {"path": "index.html"},
            ),
        ] + all_frontend_writes(start=5)

        result, _ = self.run_agent([make_response(calls=calls)])

        self.assertFalse((Path(self.tmp.name) / "escape.py").exists())
        self.assertFalse((self.pdir / ".env").exists())
        self.assertEqual(result["coder_status"], "COMPLETED")


class PartialAndFailure(CoderBase):
    def test_missing_files_are_reported_accurately(self):
        script = [
            make_response(
                calls=writes("index.html", start=1)
            ),
            make_response(content="Here is the code in prose"),
            make_response(content="Still prose"),
            make_response(content="Prose again"),
        ]

        result, _ = self.run_agent(script)

        self.assertEqual(result["coder_status"], "FAILED")
        self.assertEqual(result["coder_error_code"], "INCOMPLETE")
        self.assertTrue(result["coder_retryable"])

        for missing in ("style.css", "script.js"):
            self.assertIn(missing, result["coder_missing_files"])
            self.assertIn(missing, result["coder_error"])

        self.assertNotIn("index.html", result["coder_missing_files"])
        self.assertIn("index.html", result["coder_written_files"])

    def test_quota_error_is_fatal(self):
        error = LLMError(
            "QUOTA",
            "Free-tier quota exhausted (HTTP 429).",
        )

        result, _ = self.run_agent([error])

        self.assertEqual(result["coder_status"], "FAILED")
        self.assertEqual(result["coder_error_code"], "QUOTA")
        self.assertFalse(result["coder_retryable"])
        self.assertIn("quota", result["coder_error"].lower())

    def test_timeout_is_not_retryable(self):
        result, _ = self.run_agent(
            [LLMError("TIMEOUT", "timed out")]
        )

        self.assertEqual(result["coder_status"], "FAILED")
        self.assertFalse(result["coder_retryable"])

    def test_missing_inputs(self):
        result = coder.coder_agent(
            {"project_id": "", "user_request": ""}
        )

        self.assertEqual(result["coder_status"], "FAILED")
        self.assertFalse(result["coder_retryable"])

    def test_bad_project_id_is_non_retryable(self):
        result = coder.coder_agent(
            {"project_id": "../x", "user_request": "build X"}
        )

        self.assertEqual(result["coder_status"], "FAILED")
        self.assertFalse(result["coder_retryable"])


class Repair(CoderBase):
    def prepare_complete_project(self):
        result, _ = self.run_agent(
            [make_response(calls=all_frontend_writes())]
        )

        self.assertEqual(result["coder_status"], "COMPLETED")
        self.assertEqual(coder.get_missing_files(self.pdir), [])

    def test_repair_prompt_contains_failure_and_current_code(self):
        self.prepare_complete_project()

        fixed_html = GOOD_FILES["index.html"] + "\n<!-- fixed -->\n"
        fixed = make_tool_call(
            "repair1",
            "write_file",
            {"path": "index.html", "content": fixed_html},
        )

        result, chat = self.run_agent(
            [
                make_response(calls=[fixed]),
                make_response(content="done"),
            ],
            failure_details=(
                "Generated application verification failed.\n"
                "AssertionError: expected text was missing"
            ),
        )

        self.assertEqual(result["coder_status"], "COMPLETED")

        prompt = chat.requests[0][1]["content"]
        self.assertIn("REPAIR MODE", prompt)
        self.assertIn("expected text was missing", prompt)
        self.assertIn("--- FILE: index.html ---", prompt)
        self.assertIn("Test Application", prompt)
        self.assertIn(
            "<!-- fixed -->",
            (self.pdir / "index.html").read_text(encoding="utf-8"),
        )

    def test_repair_can_change_multiple_files(self):
        self.prepare_complete_project()

        edits = [
            make_tool_call(
                "edit1",
                "write_file",
                {
                    "path": "index.html",
                    "content": GOOD_FILES["index.html"] + "\n<!-- updated -->",
                },
            ),
            make_tool_call(
                "edit2",
                "write_file",
                {
                    "path": "script.js",
                    "content": GOOD_FILES["script.js"] + "\n// updated",
                },
            ),
        ]

        result, _ = self.run_agent(
            [
                make_response(calls=edits),
                make_response(content="done"),
            ],
            failure_details="Verification failed",
        )

        self.assertEqual(result["coder_status"], "COMPLETED")
        self.assertIn("index.html", result["coder_written_files"])
        self.assertIn("script.js", result["coder_written_files"])

    def test_repair_without_changes_is_not_success(self):
        self.prepare_complete_project()

        result, _ = self.run_agent(
            [
                make_response(content="Looks fine to me"),
                make_response(content="No changes needed"),
                make_response(content="Still fine"),
            ],
            failure_details="Verification failed",
        )

        self.assertEqual(result["coder_status"], "FAILED")
        self.assertEqual(result["coder_error_code"], "NO_CHANGES")


class AssistantRecord(unittest.TestCase):
    def test_content_is_kept_when_there_are_no_tool_calls(self):
        response = make_response(content="hello")
        record = coder.assistant_record(response.choices[0].message)

        self.assertEqual(record["content"], "hello")
        self.assertEqual(record["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
