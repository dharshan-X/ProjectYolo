import importlib
import os
import asyncio
import unittest
from contextlib import contextmanager
from unittest import mock

from session import Session


@contextmanager
def loaded_agent(**env_overrides):
    overrides = {"YOLO_HOME": "/home/dharshan/ProjectYolo/.yolo_test_home", **env_overrides}
    with mock.patch.dict(os.environ, overrides, clear=False):
        import tools.base
        import prompt_builder
        import agent as agent_module

        importlib.reload(tools.base)
        importlib.reload(prompt_builder)
        module = importlib.reload(agent_module)
        yield module


class TestAgentPromptArchitecture(unittest.TestCase):
    def test_unified_prompt_uses_template_sections(self):
        with loaded_agent(
            YOLO_SYSTEM_PROMPT_VERSION="unified",
            YOLO_SYSTEM_PROMPT_PROFILE="verbose",
        ) as agent_module:
            prompt = agent_module.get_initial_messages()[0]["content"]

        self.assertIn("Auto Basic Facts", prompt)
        self.assertNotIn("{{basic_facts}}", prompt)

    def test_compact_prompt_profile_is_short(self):
        with loaded_agent(
            YOLO_SYSTEM_PROMPT_VERSION="unified",
            YOLO_SYSTEM_PROMPT_PROFILE="compact",
        ) as agent_module:
            prompt = agent_module.get_initial_messages()[0]["content"]

        self.assertLess(len(prompt.split()), 650)

    def test_legacy_prompt_flag_keeps_current_contract(self):
        with loaded_agent(
            YOLO_SYSTEM_PROMPT_VERSION="legacy",
            YOLO_SYSTEM_PROMPT_PROFILE="verbose",
        ) as agent_module:
            prompt = agent_module.get_initial_messages()[0]["content"]

        self.assertIn("You are Yolo, an elite autonomous system controller", prompt)

    def test_identity_profile_injected_into_prompt(self):
        with loaded_agent(
            YOLO_SYSTEM_PROMPT_VERSION="unified",
            YOLO_SYSTEM_PROMPT_PROFILE="verbose",
        ) as agent_module:
            prompt = agent_module.get_initial_messages()[0]["content"]
            
        self.assertIn("Dharshan's Master AI Identity Profile", prompt)
        self.assertIn("YOLO (Cognitive Apex)", prompt)
        self.assertNotIn("{{identity_profile}}", prompt)

    def test_merge_memory_context_stays_single_system_message(self):
        with loaded_agent(
            YOLO_SYSTEM_PROMPT_VERSION="unified",
            YOLO_SYSTEM_PROMPT_PROFILE="verbose",
        ) as agent_module:
            session = Session(user_id=1, message_history=agent_module.get_initial_messages())
            agent_module._merge_memory_context_into_system_prompt(
                session,
                "[MEMORY_CONTEXT]\n- prefers concise updates",
            )

        system_messages = [m for m in session.message_history if m.get("role") == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertIn("[MEMORY_CONTEXT]", system_messages[0]["content"])
    def test_normalizer_collapses_multiple_system_messages(self):
        with loaded_agent(
            YOLO_SYSTEM_PROMPT_VERSION="unified",
            YOLO_SYSTEM_PROMPT_PROFILE="verbose",
        ) as agent_module:
            session = Session(
                user_id=1,
                message_history=[
                    {"role": "system", "content": "base"},
                    {"role": "system", "content": "[MEMORY_CONTEXT]\n- old"},
                    {"role": "system", "content": "[CONVERSATION_SUMMARY]\nsummary"},
                    {"role": "user", "content": "hello"},
                ],
            )
            agent_module._normalize_single_system_message(session)

        system_messages = [m for m in session.message_history if m.get("role") == "system"]
        assistant_messages = [
            m
            for m in session.message_history
            if m.get("role") == "assistant"
            and str(m.get("content", "")).startswith("[CONVERSATION_SUMMARY]")
        ]

        self.assertEqual(len(system_messages), 1)
        self.assertEqual(len(assistant_messages), 1)

    def test_run_turn_sends_single_system_message_to_router(self):
        with loaded_agent(
            YOLO_SYSTEM_PROMPT_VERSION="unified",
            YOLO_SYSTEM_PROMPT_PROFILE="verbose",
        ) as agent_module:
            captured = {}

            class _Delta:
                content = "ok"
                tool_calls = None

            class _Choice:
                delta = _Delta()

            class _Chunk:
                choices = [_Choice()]
                usage = None

            class _FakeStream:
                def __aiter__(self):
                    async def _gen():
                        yield _Chunk()

                    return _gen()

            async def _fake_chat_completions(*, messages, tools, tool_choice="auto", stream=False):
                captured["messages"] = messages
                return _FakeStream()

            session = Session(
                user_id=1,
                message_history=[
                    {"role": "system", "content": "base"},
                    {"role": "system", "content": "[MEMORY_CONTEXT]\n- old"},
                ],
            )

            with mock.patch.object(agent_module.router, "chat_completions", side_effect=_fake_chat_completions):
                result = asyncio.run(
                    agent_module.run_agent_turn(
                        "hello",
                        session,
                        signal_handler=None,
                        memory_service=None,
                    )
                )

        self.assertEqual(result, "ok")
        system_messages = [m for m in captured["messages"] if m.get("role") == "system"]
        self.assertEqual(len(system_messages), 1)


if __name__ == "__main__":
    unittest.main()
