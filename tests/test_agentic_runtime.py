import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pql_agent.runtime.agent import _normalize_history, run_agentic_loop


class FakeResponse:
    def __init__(self, response_id, output, output_text=""):
        self.id = response_id
        self.output = output
        self.output_text = output_text


class AgenticRuntimeTest(unittest.TestCase):
    def test_rejects_non_chat_history_roles(self):
        with self.assertRaises(ValueError):
            _normalize_history([{"role": "system", "content": "nope"}])

    def test_responses_loop_executes_retrieval_tool_and_returns_trace(self):
        create_calls = []
        fake_client = SimpleNamespace()

        def fake_create(**kwargs):
            create_calls.append(kwargs)
            if len(create_calls) == 1:
                return FakeResponse(
                    "resp_1",
                    [
                        SimpleNamespace(
                            type="function_call",
                            name="retrieve_pql_docs",
                            call_id="call_1",
                            arguments=json.dumps({"query": "PU_COUNT docs", "k": 2}),
                        )
                    ],
                )
            return FakeResponse(
                "resp_2",
                [],
                json.dumps(
                    {
                        "query": "PU_COUNT(...)",
                        "explanation": "Uses retrieved docs.",
                        "cited_chunks": ["chunk_1"],
                    }
                ),
            )

        fake_results = [
            {
                "chunk_id": "chunk_1",
                "title": "PU_COUNT",
                "term_name": "PU_COUNT",
                "chunk_type": "function",
                "url": "https://example.test",
                "text": "PU_COUNT documentation",
                "distance": 0.1,
                "similarity": 0.9,
                "boosted_similarity": 0.9,
                "term_match": True,
            }
        ]

        with (
            patch("pql_agent.runtime.agent.OpenAI", return_value=fake_client),
            patch("pql_agent.runtime.agent.retrieve_pql_docs", return_value=fake_results),
        ):
            fake_client.responses = SimpleNamespace(create=fake_create)
            answer, tool_calls = run_agentic_loop(
                "count cases",
                history=[{"role": "user", "content": "previous request"}],
                top_k=5,
            )

        self.assertEqual(answer.query, "PU_COUNT(...)")
        self.assertEqual(tool_calls[0].query, "PU_COUNT docs")
        self.assertEqual(tool_calls[0].k, 2)
        self.assertNotIn("previous_response_id", create_calls[0])
        self.assertEqual(create_calls[1]["previous_response_id"], "resp_1")
        self.assertEqual(create_calls[1]["input"][0]["type"], "function_call_output")


if __name__ == "__main__":
    unittest.main()
