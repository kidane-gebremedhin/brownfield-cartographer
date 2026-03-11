from pathlib import Path

import pytest

from repository.file_discovery import discover_files, SUPPORTED_EXTENSIONS


def test_discover_files_filters_and_hashes(tmp_path):
    (tmp_path / 'a.py').write_text('print(1)')
    (tmp_path / 'b.sql').write_text('select 1')
    (tmp_path / 'c.yaml').write_text('k: v')
    (tmp_path / 'd.md').write_text('# hi')
    (tmp_path / 'e.json').write_text('{}')
    (tmp_path / 'f.ipynb').write_text('{cells: []}')
    (tmp_path / 'x.txt').write_text('no')

    files = discover_files(tmp_path)
    exts = {f.extension for f in files}
    assert exts == {'.py', '.sql', '.yaml', '.md', '.json', '.ipynb'}
    for f in files:
        assert len(f.content_hash) == 64


def test_discover_files_skips_dirs(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / '.git' / 'a.py').write_text('x')
    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__' / 'b.py').write_text('x')
    (tmp_path / 'ok.py').write_text('x')

    files = discover_files(tmp_path)
    paths = [f.path for f in files]
    assert 'ok.py' in paths
    assert not any(p.startswith('.git') for p in paths)
    assert not any(p.startswith('__pycache__') for p in paths)


def test_hash_stable(tmp_path):
    p = tmp_path / 'a.py'
    p.write_text('same')
    h1 = discover_files(tmp_path)[0].content_hash
    h2 = discover_files(tmp_path)[0].content_hash
    assert h1 == h2


def test_hash_changes(tmp_path):
    p = tmp_path / 'a.py'
    p.write_text('v1')
    h1 = discover_files(tmp_path)[0].content_hash
    p.write_text('v2')
    h2 = discover_files(tmp_path)[0].content_hash
    assert h1 != h2


def test_discover_files_not_dir(tmp_path):
    f = tmp_path / 'a.py'
    f.write_text('x')
    with pytest.raises(NotADirectoryError):
        discover_files(f)
