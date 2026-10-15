
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import tester as t


GOOD_FILES = {
    "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test App</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <h1>Hello</h1>
    <script src="script.js"></script>
</body>
</html>
""",
    "style.css": "body { font-family: Arial, sans-serif; }\n",
    "script.js": 'console.log("Application loaded");\n',
    "README.md": "# Test App\n",
    ".gitignore": "__pycache__/\n.env\n",
}


def make_project(overrides=None):
    """Create a temporary frontend project for testing."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)

    files = {**GOOD_FILES, **(overrides or {})}

    for name, content in files.items():
        if content is None:
            continue

        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    return tmp, root


class StaticChecks(unittest.TestCase):

    def check(self, fn, overrides=None):
        tmp, root = make_project(overrides)
        self.addCleanup(tmp.cleanup)
        return fn(root)

    def test_good_project_has_no_static_errors(self):
        errors = self.check(t.check_frontend)
        self.assertEqual(errors, [])

    def test_missing_html_root_is_detected(self):
        errors = self.check(
            t.check_frontend,
            {
                "index.html": (
                    '<head><link rel="stylesheet" '
                    'href="style.css"></head>'
                    '<script src="script.js"></script>'
                )
            },
        )

        self.assertTrue(
            any("html root element" in error for error in errors),
            errors,
        )

    def test_html_must_link_assets(self):
        errors = self.check(
            t.check_frontend,
            {
                "index.html": "<html><body></body></html>",
            },
        )

        self.assertTrue(
            any("must load script.js" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("must load style.css" in error for error in errors),
            errors,
        )

    def test_empty_css_is_detected(self):
        errors = self.check(
            t.check_frontend,
            {"style.css": ""},
        )

        self.assertTrue(
            any("style.css is empty" in error for error in errors),
            errors,
        )

    def test_empty_javascript_is_detected(self):
        errors = self.check(
            t.check_frontend,
            {"script.js": ""},
        )

        self.assertTrue(
            any("script.js is empty" in error for error in errors),
            errors,
        )

    def test_missing_local_asset_is_detected(self):
        html = GOOD_FILES["index.html"].replace(
            "</head>",
            '<link rel="stylesheet" href="missing.css">\n</head>',
        )

        errors = self.check(
            t.check_frontend,
            {"index.html": html},
        )

        self.assertTrue(
            any("Referenced local asset is missing" in error
                for error in errors),
            errors,
        )

    def test_external_assets_are_allowed(self):
        html = GOOD_FILES["index.html"].replace(
            "</head>",
            '<link rel="stylesheet" '
            'href="https://example.com/app.css">\n</head>',
        )

        errors = self.check(
            t.check_frontend,
            {"index.html": html},
        )

        self.assertEqual(errors, [])

    def test_local_backend_api_is_flagged(self):
        errors = self.check(
            t.check_frontend,
            {
                "script.js": (
                    'fetch("http://127.0.0.1:8000/health");\n'
                )
            },
        )

        self.assertTrue(
            any("frontend-only output" in error for error in errors),
            errors,
        )

    def test_missing_required_files_fail(self):
        errors = self.check(
            t.check_frontend,
            {"script.js": None},
        )

        self.assertTrue(
            any("Missing required file: script.js" in error
                for error in errors),
            errors,
        )


class TesterWorkflow(unittest.TestCase):

    def test_missing_project_is_not_repairable(self):
        with mock.patch.object(
            t,
            "GENERATED_DIR",
            Path(tempfile.gettempdir()) / "tester_nonexistent_root",
        ):
            result = t.tester("does_not_exist_zzz")

        self.assertEqual(result["status"], "FAILED")
        self.assertFalse(result["repairable"])

    def test_missing_files_fail_fast_with_structured_checks(self):
        tmp, root = make_project({"script.js": None})
        self.addCleanup(tmp.cleanup)

        with mock.patch.object(t, "GENERATED_DIR", root.parent):
            result = t.tester(root.name)

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(
            result["checks"]["required_files"]["status"],
            "FAILED",
        )
        self.assertIn("script.js", result["errors"])
        self.assertEqual(
            result["checks"]["frontend"]["status"],
            "SKIPPED",
        )

    def test_valid_project_passes(self):
        tmp, root = make_project()
        self.addCleanup(tmp.cleanup)

        with mock.patch.object(t, "GENERATED_DIR", root.parent):
            result = t.tester(root.name)

        self.assertEqual(result["status"], "PASSED")
        self.assertTrue(result["repairable"])
        self.assertEqual(
            result["checks"]["required_files"]["status"],
            "PASSED",
        )
        self.assertEqual(
            result["checks"]["frontend"]["status"],
            "PASSED",
        )

    def test_invalid_project_path_is_rejected(self):
        with self.assertRaises(ValueError):
            t.get_project_dir("../outside_project")


if __name__ == "__main__":
    unittest.main()
