
import json
import socket
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from agents import runner as r


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def reachable(url):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


class RunnerLifecycle(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.gen = Path(self.tmp.name) / "generated"
        self.project = self.gen / "proj"
        self.project.mkdir(parents=True)

        (self.project / "index.html").write_text(
            "<!DOCTYPE html><html><body>Hello NexusAI</body></html>",
            encoding="utf-8",
        )
        (self.project / "style.css").write_text(
            "body { font-family: Arial; }\n",
            encoding="utf-8",
        )
        (self.project / "script.js").write_text(
            'console.log("NexusAI");\n',
            encoding="utf-8",
        )

        self.generated_patch = mock.patch.object(
            r,
            "GENERATED_DIR",
            self.gen,
        )
        self.generated_patch.start()
        self.addCleanup(self.generated_patch.stop)

        self.addCleanup(r.stop_application)

        self.port = free_port()

    def test_static_frontend_starts_and_responds(self):
        result = r.runner("proj", frontend_port=self.port)

        self.assertEqual(result["status"], "RUNNING", result["errors"])
        self.assertEqual(
            result["frontend_url"],
            f"http://127.0.0.1:{self.port}",
        )
        self.assertEqual(result["application_url"], result["frontend_url"])
        self.assertIsNone(result["backend_url"])
        self.assertTrue(reachable(result["frontend_url"] + "/"))

        with urllib.request.urlopen(
            result["frontend_url"] + "/",
            timeout=2,
        ) as response:
            body = response.read().decode("utf-8")

        self.assertIn("Hello NexusAI", body)

        state_path = self.gen / r.STATE_FILE_NAME
        self.assertTrue(state_path.is_file())

        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["project_id"], "proj")
        self.assertEqual(state["frontend_port"], self.port)
        self.assertEqual(len(state["pids"]), 1)

    def test_stop_application_stops_server_and_removes_state(self):
        result = r.runner("proj", frontend_port=self.port)

        self.assertEqual(result["status"], "RUNNING", result["errors"])

        stopped = r.stop_application("proj")

        self.assertEqual(len(stopped["stopped"]), 1)
        self.assertFalse((self.gen / r.STATE_FILE_NAME).exists())

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not reachable(result["frontend_url"] + "/"):
                break
            time.sleep(0.1)

        self.assertFalse(reachable(result["frontend_url"] + "/"))

    def test_missing_project_fails(self):
        result = r.runner("does_not_exist")

        self.assertEqual(result["status"], "FAILED")
        self.assertIsNone(result["frontend_url"])
        self.assertIn("does not exist", result["errors"])

    def test_missing_index_html_fails(self):
        (self.project / "index.html").unlink()

        result = r.runner("proj")

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("Missing generated UI", result["errors"])
        self.assertIsNone(result["frontend_url"])

    def test_foreign_process_on_requested_port_gives_clear_error(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", self.port))
        blocker.listen(1)
        self.addCleanup(blocker.close)

        result = r.runner("proj", frontend_port=self.port)

        self.assertEqual(result["status"], "FAILED")
        self.assertIn(f"port {self.port} is in use", result["errors"])

    def test_previous_run_is_released_automatically(self):
        first = r.runner("proj", frontend_port=self.port)

        self.assertEqual(first["status"], "RUNNING", first["errors"])

        second_port = free_port()
        second = r.runner("proj", frontend_port=second_port)

        self.assertEqual(second["status"], "RUNNING", second["errors"])
        self.assertNotEqual(first["frontend_pid"], second["frontend_pid"])

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not reachable(first["frontend_url"] + "/"):
                break
            time.sleep(0.1)

        self.assertFalse(reachable(first["frontend_url"] + "/"))
        self.assertTrue(reachable(second["frontend_url"] + "/"))

    def test_stop_when_nothing_is_running(self):
        result = r.stop_application()

        self.assertEqual(result["stopped"], [])

    def test_wrong_project_does_not_stop_recorded_application(self):
        result = r.runner("proj", frontend_port=self.port)

        self.assertEqual(result["status"], "RUNNING", result["errors"])

        stopped = r.stop_application("another_project")

        self.assertEqual(stopped["stopped"], [])
        self.assertTrue(reachable(result["frontend_url"] + "/"))


if __name__ == "__main__":
    unittest.main()
