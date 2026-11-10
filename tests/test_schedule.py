from datetime import datetime

from printtool.core import schedule


def test_schedule_windows_builds_schtasks_command(monkeypatch):
    monkeypatch.setattr(schedule.sys, "platform", "win32")

    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(schedule.subprocess, "run", fake_run)

    at = datetime(2026, 11, 6, 9, 0)
    success, message = schedule.schedule_print(at, ["print", "doc.pdf"])

    assert success
    assert "schtasks" in captured["cmd"]
    assert "/create" in captured["cmd"]
    assert "09:00" in captured["cmd"]
    assert "11/06/2026" in captured["cmd"]


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
