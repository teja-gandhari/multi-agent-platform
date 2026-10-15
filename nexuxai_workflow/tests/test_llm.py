
import unittest
from unittest.mock import patch

from openai import APITimeoutError

from services import llm


def make_response(content="ok"):
    class Message:
        def __init__(self):
            self.content = content
            self.tool_calls = None

    class Choice:
        def __init__(self):
            self.message = Message()
            self.finish_reason = "stop"

    class Usage:
        prompt_tokens = 10
        completion_tokens = 5

    class Response:
        def __init__(self):
            self.choices = [Choice()]
            self.usage = Usage()

    return Response()


class RetryPolicy(unittest.TestCase):
    def setUp(self):
        self.client_patcher = patch("services.llm.get_client")
        self.mock_get_client = self.client_patcher.start()
        self.addCleanup(self.client_patcher.stop)

        self.sleep_patcher = patch("services.llm.time.sleep")
        self.mock_sleep = self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

        self.responses = []
        self.calls = 0

        class Completions:
            def create(inner_self, **kwargs):
                self.calls += 1
                result = self.responses.pop(0)

                if isinstance(result, BaseException):
                    raise result

                return result

        class Chat:
            completions = Completions()

        class Client:
            chat = Chat()

        self.mock_get_client.return_value = Client()

        self.model_patcher = patch(
            "services.llm.settings.model_for",
            return_value="gemini-3.8-flash",
        )
        self.model_patcher.start()
        self.addCleanup(self.model_patcher.stop)

        self.timeout_patcher = patch(
            "services.llm.settings.read_timeout_for",
            return_value=30,
        )
        self.timeout_patcher.start()
        self.addCleanup(self.timeout_patcher.stop)

        self.tokens_patcher = patch(
            "services.llm.settings.max_tokens_for",
            return_value=1000,
        )
        self.tokens_patcher.start()
        self.addCleanup(self.tokens_patcher.stop)

        self.reasoning_patcher = patch(
            "services.llm.settings.reasoning_effort_for",
            return_value=None,
        )
        self.reasoning_patcher.start()
        self.addCleanup(self.reasoning_patcher.stop)

        self.api_key_patcher = patch(
            "services.llm.settings.api_key",
            return_value="test-key",
        )
        self.api_key_patcher.start()
        self.addCleanup(self.api_key_patcher.stop)

        self.connect_timeout_patcher = patch(
            "services.llm.settings.CONNECT_TIMEOUT",
            5,
            create=True,
        )
        self.connect_timeout_patcher.start()
        self.addCleanup(self.connect_timeout_patcher.stop)

        self.base_url_patcher = patch(
            "services.llm.settings.GEMINI_OPENAI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            create=True,
        )
        self.base_url_patcher.start()
        self.addCleanup(self.base_url_patcher.stop)

        self.log_patcher = patch("services.llm.CALL_LOG", [])
        self.log_patcher.start()
        self.addCleanup(self.log_patcher.stop)

    def run_chat(self, responses):
        self.responses = list(responses)
        self.calls = 0

        try:
            response = llm.chat(
                "planner",
                [{"role": "user", "content": "test"}],
            )
            return response, None, self.calls, [
                call.args[0] for call in self.mock_sleep.call_args_list
            ]
        except llm.LLMError as err:
            return None, err, self.calls, [
                call.args[0] for call in self.mock_sleep.call_args_list
            ]

    def test_timeout_retries_then_succeeds(self):
        self.mock_sleep.reset_mock()

        _, err, calls, sleeps = self.run_chat([
            APITimeoutError("t"),
            APITimeoutError("t"),
            make_response("success"),
        ])

        self.assertIsNone(err)
        self.assertEqual(calls, 3)
        self.assertEqual(sleeps, [3.0, 6.0])

    def test_timeout_stops_after_retry_limit(self):
        self.mock_sleep.reset_mock()

        _, err, calls, sleeps = self.run_chat([
            APITimeoutError("t"),
            APITimeoutError("t"),
            APITimeoutError("t"),
            APITimeoutError("t"),
        ])

        self.assertIsNotNone(err)
        self.assertEqual(err.code, "TIMEOUT")
        self.assertEqual(calls, 4)
        self.assertEqual(sleeps, [3.0, 6.0, 12.0])


if __name__ == "__main__":
    unittest.main()
