from unittest.mock import MagicMock

from webapp import worker


def test_worker_main_waits_for_shutdown(monkeypatch):
    manager = MagicMock()
    shutdown_requested = MagicMock()

    monkeypatch.setattr(worker, "FilePollingJobManager", MagicMock(return_value=manager))
    monkeypatch.setattr(worker, "start_cleanup_scheduler", MagicMock())
    monkeypatch.setattr(worker.threading, "Event", MagicMock(return_value=shutdown_requested))
    monkeypatch.setattr(worker.signal, "signal", MagicMock())

    assert worker.main() == 0
    manager.start.assert_called_once_with()
    shutdown_requested.wait.assert_called_once_with()
    manager.stop.assert_called_once_with()
