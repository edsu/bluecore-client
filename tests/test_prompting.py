"""Credential prompts must not collide with the spinner.

A rich status redraws its line continuously, so a prompt issued while one is
running is overwritten -- both the question and the characters being typed
disappear. These cover the two halves of the fix: the spinner can be stood
down, and no command asks for credentials while one is running.
"""

import ast
import pathlib

import pytest

from bluecore_client.cli import ui

COMMANDS = pathlib.Path("bluecore_client/cli/commands")


class FakeStatus:
    """Stands in for a rich Status, recording start/stop."""

    def __init__(self):
        self.stops = 0
        self.starts = 0

    def stop(self):
        self.stops += 1

    def start(self):
        self.starts += 1


class TestPause:
    def test_pause_stops_and_restarts_the_spinner(self, monkeypatch):
        status = FakeStatus()
        monkeypatch.setattr(ui, "_active_status", status)

        with ui.pause():
            assert status.stops == 1
            assert status.starts == 0

        assert status.starts == 1

    def test_pause_restarts_even_if_the_body_raises(self, monkeypatch):
        status = FakeStatus()
        monkeypatch.setattr(ui, "_active_status", status)

        with pytest.raises(RuntimeError), ui.pause():
            raise RuntimeError("boom")

        assert status.starts == 1

    def test_pause_is_harmless_with_no_spinner(self, monkeypatch):
        monkeypatch.setattr(ui, "_active_status", None)

        with ui.pause():
            pass  # must not raise


class TestWorkingTracksTheSpinner:
    def test_no_spinner_is_tracked_when_stderr_is_not_a_terminal(self):
        """Which is the case under pytest, so nothing should be registered."""
        with ui.working("thinking"):
            assert ui._active_status is None

    def test_the_tracked_status_is_cleared_afterwards(self, monkeypatch):
        created = _AsContext(FakeStatus())
        monkeypatch.setattr(ui, "err", _FakeConsole([created]))

        with ui.working("thinking"):
            assert ui._active_status is created

        assert ui._active_status is None

    def test_a_nested_spinner_restores_the_outer_one(self, monkeypatch):
        outer = _AsContext(FakeStatus())
        inner = _AsContext(FakeStatus())
        monkeypatch.setattr(ui, "err", _FakeConsole([outer, inner]))

        with ui.working("outer"):
            with ui.working("inner"):
                assert ui._active_status is inner
            assert ui._active_status is outer, "the outer spinner is running again"


class _FakeConsole:
    """A terminal-like console handing out prepared statuses.

    Console.is_terminal is a read-only property, so the console has to be
    replaced rather than patched.
    """

    is_terminal = True

    def __init__(self, statuses):
        self._statuses = iter(statuses)

    def status(self, *args, **kwargs):
        return next(self._statuses)

    def print(self, *args, **kwargs):
        pass


class _AsContext:
    """Wraps a FakeStatus so `with status:` works."""

    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self.status

    def __exit__(self, *exc):
        return False

    def stop(self):
        self.status.stop()

    def start(self):
        self.status.start()


class TestNoCommandPromptsUnderASpinner:
    """A structural check, so this can't quietly come back.

    Rather than testing the symptom, this asserts the invariant: authentication
    -- which may prompt -- is resolved before any spinner starts.
    """

    def source_files(self):
        root = pathlib.Path(__file__).parent.parent / "src" / COMMANDS
        files = sorted(root.glob("*.py"))
        assert files, f"no command modules found under {root}"
        return files

    def test_require_auth_is_never_requested_inside_ui_working(self):
        offenders = []

        for path in self.source_files():
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.With):
                    continue
                if not any(_is_working(item.context_expr) for item in node.items):
                    continue
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call) and _asks_for_auth(inner):
                        offenders.append(f"{path.name}:{inner.lineno}")

        assert offenders == [], (
            "these ask for credentials inside a ui.working() spinner, which "
            f"would redraw over the prompt: {offenders}"
        )

    def test_the_check_can_actually_detect_the_problem(self):
        """Guards against the scan silently matching nothing."""
        tree = ast.parse("with ui.working('x'):\n    client(require_auth=True).do()\n")
        found = [
            inner
            for node in ast.walk(tree)
            if isinstance(node, ast.With)
            and any(_is_working(i.context_expr) for i in node.items)
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call) and _asks_for_auth(inner)
        ]

        assert len(found) == 1


def _is_working(expr) -> bool:
    """Whether an expression is a call to ui.working(...)."""
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "working"
    )


def _asks_for_auth(call: ast.Call) -> bool:
    """Whether a call passes require_auth=True."""
    return any(
        keyword.arg == "require_auth"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )
