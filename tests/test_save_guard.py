import asyncio
import sys
import unittest
from unittest import mock

from app import save_guard

SHOWS = {"add_show", "update_show", "show_status"}


class ClaimTests(unittest.TestCase):
    def test_claims(self):
        for reply in (
            "I've added *Hackers* and *Jennifer’s Body* to your want-to-watch list.",
            "I added both to your list.",
            "I have also logged that.",
            "Logged your 45-minute bass practice. Keep it up!",
            "Got it! I've updated your progress.",
            "Noted. You're on episode 6 of Silicon Valley.",
            "Done, added to your groceries.",
            "That's noted for today!",
            "Both movies have been added.",
            "You're now marked as watching it.",
            "Great job. Marked as done.",
        ):
            with self.subTest(reply=reply):
                self.assertTrue(save_guard.claims(reply, SHOWS))

    def test_not_claims(self):
        for reply in (
            "I didn't save that, because Severance isn't on your watch list. Want me to add it?",
            "I haven't added anything yet.",
            "I can't save that from chat. It goes in the fitness section of your daily note.",
            "**Nothing was saved.**",
            "Would you like me to add it?",
            "Once you've added it, tell me.",
            "That's a great movie!",
            "You're currently watching Strange New Worlds.",
        ):
            with self.subTest(reply=reply):
                self.assertFalse(save_guard.claims(reply, SHOWS))

    def test_without_save_tools_it_must_be_about_the_users_things(self):
        self.assertFalse(save_guard.claims("I've added a comment to the function.", set()))
        self.assertTrue(save_guard.claims("I've added milk to your list.", set()))

    def test_which_turns_are_checked(self):
        self.assertTrue(save_guard.should_check("lets add the movies Hackers", SHOWS))
        self.assertTrue(save_guard.should_check("yes!", SHOWS))
        self.assertTrue(save_guard.should_check("add milk", set()))
        self.assertFalse(save_guard.should_check("what was I watching?", SHOWS))
        self.assertFalse(save_guard.should_check("write me a poem", set()))

    def test_what_counts_as_saved(self):
        self.assertTrue(save_guard.saved("add_show", 'Added "Hackers" (movie).'))
        for tool, result in (
            ("show_status", "Currently watching: nothing."),
            ("add_show", "NOT ADDED. Already there"),
            ("update_show", "NOT SAVED. Nothing changed"),
            ("log_chore", "x. Nothing was logged."),
            ("complete_task", 'No open task matching "x" found.'),
            ("complete_todo_item", "Multiple items match"),
            ("log_to_daily_note", "Not logged: refused"),
        ):
            with self.subTest(tool=tool, result=result):
                self.assertFalse(save_guard.saved(tool, result))

    def test_fresh_context(self):
        talk = [{"role": "system", "content": "S"}] + [{"role": r, "content": c} for r, c in (
            ("user", "old"), ("assistant", "I've added it"), ("user", "add two movies to my watch list"),
            ("assistant", "Want me to?"), ("user", "yes!"),
        )]
        short = save_guard.fresh_context(talk)
        self.assertEqual([m["content"] for m in short[1:]], ["add two movies to my watch list", "Want me to?", "yes!"])
        self.assertIn("nothing was saved", short[0]["content"])
        long = save_guard.fresh_context(talk[:4])
        self.assertEqual([m["content"] for m in long[1:]], ["add two movies to my watch list"])
        self.assertEqual(talk[0]["content"], "S")


def call(name, **arguments):
    return {"function": {"name": name, "arguments": arguments}}


class TurnTests(unittest.TestCase):
    """run_chat_stream with a scripted model and stand-in tools."""

    @classmethod
    def setUpClass(cls):
        stubbed = []
        for _ in range(30):
            try:
                from app import chat

                break
            except ModuleNotFoundError as missing:
                sys.modules[missing.name] = mock.MagicMock()
                stubbed.append(missing.name)
        for name in stubbed:
            sys.modules.pop(name, None)
        cls.chat = chat

    def run_chat(self, message, *script, result="Added it."):
        """`script` is one model response per request: text, or tool calls."""
        responses, requests, ran = list(script), [], []

        async def model(messages, name, think, tools):
            requests.append([dict(m) for m in messages])
            step = responses.pop(0)
            if isinstance(step, str):
                yield ("content", step)
            else:
                yield ("tool_calls", step)

        def add_show(**kwargs):
            ran.append(kwargs)
            return result

        async def go():
            history = [
                {"role": "user", "content": "add Dune to my watch list"},
                {"role": "assistant", "content": "I've added Dune."},
                {"role": "user", "content": message},
            ]
            return [event async for event in self.chat.run_chat_stream(history)]

        tools = [{"function": {"name": "add_show"}}]
        with mock.patch.object(self.chat, "_stream_ollama", model), mock.patch.object(
            self.chat, "select_tools", return_value=tools
        ), mock.patch.dict(self.chat.TOOL_HANDLERS, {"add_show": add_show}), mock.patch.object(
            self.chat.habit_chat, "report_note", return_value=None
        ):
            events = asyncio.run(go())
        text = "".join(value for kind, value in events if kind == "content")
        return text, requests, ran

    def test_a_real_save_passes_straight_through(self):
        text, requests, ran = self.run_chat("add Hackers", [call("add_show", title="Hackers")], "I've added Hackers.")
        self.assertEqual((text, len(requests), len(ran)), ("I've added Hackers.", 2, 1))

    def test_a_false_claim_is_retried_fresh_and_saves(self):
        text, requests, ran = self.run_chat(
            "add Hackers to my watch list", "I've added Hackers.",
            [call("add_show", title="Hackers")], "Added Hackers to your list.",
        )
        self.assertEqual((text, len(ran)), ("Added Hackers to your list.", 1))
        self.assertEqual([m["role"] for m in requests[1]], ["system", "user"])
        self.assertIn("nothing was saved", requests[1][0]["content"])

    def test_two_false_claims_say_nothing_was_saved(self):
        text, requests, ran = self.run_chat("add Hackers", "I've added Hackers.", "I've added Hackers now.")
        self.assertEqual((text, len(requests), ran), (save_guard.NOTHING_SAVED, 2, []))

    def test_a_failed_save_claimed_as_done_is_caught(self):
        text, _, ran = self.run_chat(
            "add Hackers", [call("add_show", title="Hackers")], "I've added Hackers.",
            "I've added Hackers.", result="NOT ADDED. Already there",
        )
        self.assertEqual((text, len(ran)), (save_guard.NOTHING_SAVED, 1))

    def test_honest_replies_and_questions_are_left_alone(self):
        honest = "I didn't save that. Want me to add it?"
        self.assertEqual(self.run_chat("add Hackers", honest)[0], honest)
        claim = "Yes, I've added it."
        text, requests, _ = self.run_chat("did you add it?", claim)
        self.assertEqual((text, len(requests)), (claim, 1))


if __name__ == "__main__":
    unittest.main()
