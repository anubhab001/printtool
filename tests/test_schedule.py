from datetime import datetime

from printtool.core import schedule


def test_schedule_windows_registers_task_with_iso_date(monkeypatch):
    monkeypatch.setattr(schedule.sys, "platform", "win32")

    captured = []

    def fake_run(cmd, capture_output, text, env):
        captured.append(env)

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(schedule.subprocess, "run", fake_run)

    at = datetime(2026, 11, 6, 9, 0)
    assert schedule.schedule_print(at, ["print", "doc.pdf"])[0]
    assert schedule.schedule_print(at, ["print", "other.pdf"])[0]
    # The date is ISO, whatever the system's date format.
    assert captured[0]["PT_AT"] == "2026-11-06T09:00:00"
    assert "doc.pdf" in captured[0]["PT_ARGS"]
    # Two files at the same minute get two tasks.
    assert captured[0]["PT_NAME"] != captured[1]["PT_NAME"]


def test_schedule_makes_existing_paths_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "report.pdf").write_text("x")
    out = schedule.absolute_files(["print", "report.pdf", "--printer", "Office"])
    assert out[1] == str(tmp_path / "report.pdf")
    assert out[3] == "Office"


def test_schedule_unix_builds_at_command(monkeypatch):
    monkeypatch.setattr(schedule.sys, "platform", "linux")
    monkeypatch.setattr(schedule.shutil, "which", lambda name: "/usr/bin/at")

    captured = {}

    def fake_run(cmd, input, capture_output, text):
        captured["cmd"] = cmd
        captured["input"] = input

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(schedule.subprocess, "run", fake_run)

    at = datetime(2026, 11, 6, 9, 0)
    success, message = schedule.schedule_print(at, ["print", "doc.pdf"])

    assert success
    assert captured["cmd"][0] == "at"
    assert "09:00" in captured["cmd"][1]
    assert "doc.pdf" in captured["input"]


def test_schedule_unix_reports_missing_at(monkeypatch):
    monkeypatch.setattr(schedule.sys, "platform", "linux")
    monkeypatch.setattr(schedule.shutil, "which", lambda name: None)

    success, message = schedule.schedule_print(datetime(2026, 11, 6, 9, 0), ["print", "doc.pdf"])

    assert not success
    assert "at" in message.lower()
