# tests/test_smoke.py
from hatop.__main__ import main


def test_main_runs_without_error(capsys):
    main()
    captured = capsys.readouterr()
    assert "hatop" in captured.out
