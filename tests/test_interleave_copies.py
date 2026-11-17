from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from printtool.core.models import PrintJob, PrintSettings
from printtool.gui.app import MainWindow


def test_interleave_copies_round_robins_across_jobs() -> None:
    job_a = PrintJob(path=Path("a.pdf"), settings=PrintSettings(copies=2))
    job_b = PrintJob(path=Path("b.pdf"), settings=PrintSettings(copies=1))
    job_c = PrintJob(path=Path("c.pdf"), settings=PrintSettings(copies=2))

    calls = MainWindow._interleave_copies([job_a, job_b, job_c])

    assert [c.path.name for c in calls] == ["a.pdf", "b.pdf", "c.pdf", "a.pdf", "c.pdf"]
    assert all(c.settings.copies == 1 for c in calls)


def test_interleave_copies_preserves_job_id_for_status_updates() -> None:
    job = PrintJob(path=Path("a.pdf"), settings=PrintSettings(copies=3))

    calls = MainWindow._interleave_copies([job])

    assert all(c.job_id == job.job_id for c in calls)
    assert len(calls) == 3
