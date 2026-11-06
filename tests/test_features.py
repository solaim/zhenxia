import json
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from zhenxia import features


@pytest.mark.parametrize('value', [None, '', '0', 'true', '1'])
def test_switch_is_captured_once_and_requires_explicit_one(value):
    env = dict(os.environ)
    env.pop('ZHENXIA_ENABLE_BANGUMI', None)
    if value is not None:
        env['ZHENXIA_ENABLE_BANGUMI'] = value
    code = (
        'import os,json; from zhenxia import features; '
        'before=features.BANGUMI_ENABLED; '
        'os.environ["ZHENXIA_ENABLE_BANGUMI"]="0" if before else "1"; '
        'print(json.dumps([before,features.BANGUMI_ENABLED]))'
    )
    result = subprocess.run([sys.executable, '-c', code], env=env, check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [value == '1', value == '1']


def test_cli_opt_in_reaches_app_and_worker(monkeypatch, tmp_path):
    from zhenxia import __main__ as entry
    monkeypatch.setenv('ZHENXIA_ENABLE_BANGUMI', '0')
    monkeypatch.setattr(features, 'BANGUMI_ENABLED', False)
    monkeypatch.setattr(entry, 'configure_runtime', lambda: None)
    monkeypatch.setattr(entry, 'frozen', lambda: False)
    monkeypatch.setattr(entry, 'load_config', lambda path: object())
    monkeypatch.setattr(sys, 'argv', ['zhenxia', '--enable-bangumi', '--config', str(tmp_path / 'config.yml')])
    app = MagicMock()
    monkeypatch.setattr(entry, 'build_app', app)
    server = MagicMock()
    monkeypatch.setattr(entry.uvicorn, 'Server', lambda config: server)
    monkeypatch.setattr(entry.uvicorn, 'Config', lambda *a, **kw: object())
    entry.main()
    assert features.BANGUMI_ENABLED
    app.assert_called_once()
    server.run.assert_called_once()
    result = subprocess.run([sys.executable, '-c',
                             'from zhenxia.features import BANGUMI_ENABLED; print(BANGUMI_ENABLED)'],
                            check=True, capture_output=True, text=True)
    assert result.stdout.strip() == 'True'
    assert 'bangumi' not in (tmp_path / 'config.yml').read_text(encoding='utf-8')


def test_cli_option_hidden_from_help(monkeypatch, capsys):
    from zhenxia import __main__ as entry
    monkeypatch.setattr(entry, 'configure_runtime', lambda: None)
    monkeypatch.setattr(sys, 'argv', ['zhenxia', '--help'])
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 0
    assert 'bangumi' not in capsys.readouterr().out
