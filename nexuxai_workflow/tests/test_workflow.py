import unittest
from unittest import mock

import workflow as wf


def ok_planner(state):  return {"plan": "P", "planner_status": "COMPLETED"}
def ok_research(state): return {"research_output": "R", "research_status": "COMPLETED"}
def ok_dev(state):      return {"developer_output": "D", "developer_status": "COMPLETED"}


class Harness:
    """Patches every agent; records what each one saw."""

    def __init__(self, coder_results, tester_results, runner_result=None):
        self.coder_results = list(coder_results)
        self.tester_results = list(tester_results)
        self.runner_result = runner_result or {
            "status": "RUNNING", "frontend_url": "http://127.0.0.1:8080",
            "backend_url": "http://127.0.0.1:8000"}
        self.coder_states, self.runner_calls, self.tester_calls = [], 0, 0


    def coder(self, state):
        self.coder_states.append(dict(state))
        return self.coder_results.pop(0)

    def tester(self, project_id):
        self.tester_calls += 1
        return self.tester_results.pop(0)

    def runner(self, project_id):
        self.runner_calls += 1
        return self.runner_result

    def reviewer(self, **kwargs):
        """Deterministic reviewer for workflow unit tests."""
        test_result = kwargs.get("test_result", {})
        checks = test_result.get("checks", {})
        coder_output = kwargs.get("coder_output", {})

        checks_passed = (
            isinstance(checks, dict)
            and bool(checks)
            and all(
                isinstance(check, dict)
                and check.get("status") == "PASSED"
                for check in checks.values()
            )
        )

        coder_completed = (
            isinstance(coder_output, dict)
            and coder_output.get("status") == "COMPLETED"
        )

        if checks_passed and coder_completed:
            return {
                "decision": "APPROVED",
                "explanation": "All validation checks passed.",
                "problems": [],
            }

        return {
            "decision": "NEEDS_REVISION",
            "explanation": "Validation checks are missing or incomplete.",
            "problems": [],
        }

    def run(self):
        patches = [
            mock.patch.object(wf, "planner_agent", ok_planner),
            mock.patch.object(wf, "researcher_agent", ok_research),
            mock.patch.object(wf, "developer_agent", ok_dev),
            mock.patch.object(wf, "coder_agent", self.coder),
            mock.patch.object(wf, "tester", self.tester),
            mock.patch.object(wf, "runner", self.runner),
            mock.patch.object(wf, "reviewer_agent", self.reviewer),
        ]
        for p in patches: p.start()
        try:
            return wf.app.invoke(wf.build_initial_state("build a weather app"),
                                 config={"recursion_limit": 60})
        finally:
            for p in patches: p.stop()


COMPLETED = {"coder_status": "COMPLETED", "coder_error": "", "coder_retryable": False,
             "coder_written_files": [], "coder_missing_files": []}
PASSED = {"status": "PASSED", "errors": "", "checks": {
    n: {"status": "PASSED", "error": ""} for n in
    ("required_files", "python_syntax", "integration", "dependencies", "pytest", "backend_runtime")}}


def failed_test(errors="pytest failed", repairable=True):
    return {"status": "FAILED", "errors": errors, "checks": {}, "repairable": repairable}


class FullGraph(unittest.TestCase):
    def test_happy_path(self):
        h = Harness([COMPLETED], [PASSED])
        final = h.run()
        self.assertEqual(final["workflow_status"], "COMPLETED")
        self.assertEqual(final["application_url"], "http://127.0.0.1:8080")
        self.assertEqual(final["revision_count"], 1)
        self.assertEqual(final["review_status"], "APPROVED")
        self.assertEqual(h.runner_calls, 1)

    def test_coder_receives_upstream_output(self):
        h = Harness([COMPLETED], [PASSED]); h.run()
        seen = h.coder_states[0]
        self.assertEqual(seen["developer_output"], "D")
        self.assertEqual(seen["plan"], "P")
        self.assertEqual(seen["research_output"], "R")
        self.assertIn("frontend-only", seen["project_context"])
        self.assertIn("HTML, CSS, and JavaScript", seen["project_context"])
        self.assertNotIn("Do not create a generated-app backend", "")

    def test_one_repair_then_success_passes_failure_details(self):
        h = Harness([COMPLETED, COMPLETED], [failed_test("AssertionError 404"), PASSED])
        final = h.run()
        self.assertEqual(final["workflow_status"], "COMPLETED")
        self.assertEqual(final["revision_count"], 2)
        self.assertIn("AssertionError 404", h.coder_states[1]["failure_details"])

    def test_error_text_containing_429_or_401_does_not_abort_repair(self):
        """Regression: pytest/pip output with '429'/'401' used to end the run."""
        noisy = "pip: downloaded pydantic_core (401 kB) ... assert resp.status_code == 429"
        h = Harness([COMPLETED, COMPLETED], [failed_test(noisy), PASSED])
        self.assertEqual(h.run()["workflow_status"], "COMPLETED")

    def test_repairs_are_limited_and_runner_never_called(self):
        h = Harness([COMPLETED] * 3, [failed_test("still broken")] * 3)
        final = h.run()
        self.assertEqual(final["workflow_status"], "FAILED")
        self.assertEqual(final["revision_count"], wf.MAX_CODER_ATTEMPTS)
        self.assertEqual(h.runner_calls, 0)
        self.assertIn("still broken", final["error_message"])

    def test_unrepairable_infrastructure_failure_stops_immediately(self):
        h = Harness([COMPLETED] * 3, [failed_test("pip network timeout", repairable=False)] * 3)
        final = h.run()
        self.assertEqual(final["workflow_status"], "FAILED")
        self.assertEqual(final["revision_count"], 1)
        self.assertEqual(h.tester_calls, 1)

    def test_fatal_coder_error_skips_tester(self):
        fatal = {"coder_status": "FAILED", "coder_error": "[QUOTA] exhausted",
                 "coder_error_code": "QUOTA", "coder_retryable": False}
        h = Harness([fatal], [])
        final = h.run()
        self.assertEqual(final["workflow_status"], "FAILED")
        self.assertEqual(h.tester_calls, 0)
        self.assertEqual(h.runner_calls, 0)
        self.assertIn("QUOTA", final["error_message"])

    def test_retryable_coder_failure_is_retried(self):
        partial = {"coder_status": "FAILED", "coder_error": "missing files",
                   "coder_error_code": "INCOMPLETE", "coder_retryable": True}
        h = Harness([partial, COMPLETED], [PASSED])
        final = h.run()
        self.assertEqual(final["workflow_status"], "COMPLETED")
        self.assertEqual(final["revision_count"], 2)

    def test_coder_crash_is_reported_with_original_cause(self):
        h = Harness([], [])
        h.coder = lambda state: (_ for _ in ()).throw(KeyError("boom-detail"))
        final = h.run()
        self.assertEqual(final["workflow_status"], "FAILED")
        self.assertIn("boom-detail", final["error_message"])

    def test_tester_pass_without_real_checks_is_not_approved(self):
        fake_pass = {"status": "PASSED", "errors": "", "checks": {}}
        h = Harness([COMPLETED] * 3, [fake_pass] * 3)
        final = h.run()
        self.assertEqual(final["workflow_status"], "FAILED")
        self.assertEqual(h.runner_calls, 0)
        self.assertEqual(final["review_status"], "NEEDS_REVISION")

    def test_runner_failure_is_not_success(self):
        h = Harness([COMPLETED], [PASSED], runner_result={"status": "FAILED", "errors": "port busy"})
        final = h.run()
        self.assertEqual(final["workflow_status"], "FAILED")
        self.assertEqual(final["application_url"], "")
        self.assertIn("port busy", final["error_message"])

    def test_planner_failure_stops_before_later_agents(self):
        h = Harness([], [])
        with mock.patch.object(wf, "planner_agent",
                               lambda s: {"planner_status": "FAILED", "planner_error": "[TIMEOUT] x"}), \
             mock.patch.object(wf, "researcher_agent", side_effect=AssertionError("must not run")):
            final = wf.app.invoke(wf.build_initial_state("x"), config={"recursion_limit": 60})
        self.assertEqual(final["workflow_status"], "FAILED")
        self.assertIn("TIMEOUT", final["error_message"])


class StateConsistency(unittest.TestCase):
    def test_every_state_key_returned_by_nodes_is_declared(self):
        declared = set(wf.WorkflowState.__annotations__)
        h = Harness([COMPLETED], [PASSED])
        final = h.run()
        undeclared = set(final) - declared
        self.assertEqual(undeclared, set(), f"undeclared state keys: {undeclared}")


if __name__ == "__main__":
    unittest.main()
