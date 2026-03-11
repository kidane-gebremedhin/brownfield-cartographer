import tempfile
from pathlib import Path

import pytest

from repository.loader import load_repository, is_github_url, LoadedRepository


def test_is_github_url():
    assert is_github_url('https://github.com/org/repo')
    assert is_github_url('https://github.com/org/repo.git')
    assert is_github_url('git@github.com:org/repo.git')
    assert not is_github_url('https://gitlab.com/org/repo')


def test_load_repository_empty():
    with pytest.raises(ValueError):
        load_repository('')


def test_load_repository_missing_local_path(tmp_path):
    missing = tmp_path / 'nope'
    with pytest.raises(FileNotFoundError):
        load_repository(str(missing))


def test_load_repository_not_dir(tmp_path):
    f = tmp_path / 'f.txt'
    f.write_text('x')
    with pytest.raises(NotADirectoryError):
        load_repository(str(f))


def test_load_repository_invalid_url():
    with pytest.raises(ValueError, match='Unsupported URL'):
        load_repository('https://gitlab.com/org/repo')


def test_load_repository_clone_mock(monkeypatch, tmp_path):
    calls = []

    def fake_run_cmd(args, **kwargs):
        calls.append(args)
        return type('R', (), {'stdout': '', 'stderr': '', 'returncode': 0})()

    monkeypatch.setattr('repository.loader.run_cmd', fake_run_cmd)

    sys_tmp = Path(tempfile.gettempdir()).resolve()
    temp_parent = sys_tmp / 'cartographer_test'
    loaded = load_repository('https://github.com/octocat/Hello-World.git', ref='main', temp_parent=temp_parent)
    assert isinstance(loaded, LoadedRepository)
    assert loaded.is_temporary
    assert loaded.root.exists()
    assert calls and calls[0][0] == 'git'
