import pytest

from zhenxia.network import proxy_for, validate_proxy


def test_network_precedence_and_explicit_direct(monkeypatch):
    for key in ('ZHENXIA_PROXY', 'ZHENXIA_PROXY_YOUTUBE'):
        monkeypatch.delenv(key, raising=False)
    config = {'proxy':'http://configured:8080'}
    assert proxy_for(config, 'youtube') == config['proxy']
    monkeypatch.setenv('HTTPS_PROXY', 'http://implicit:1234')
    assert proxy_for({}, 'youtube') == ''
    monkeypatch.setenv('ZHENXIA_PROXY', 'http://global:8080')
    assert proxy_for(config, 'youtube') == 'http://global:8080'
    monkeypatch.setenv('ZHENXIA_PROXY_YOUTUBE', '')
    assert proxy_for(config, 'youtube') == ''
    assert proxy_for(config, 'douyin') == 'http://global:8080'
    monkeypatch.setenv('ZHENXIA_PROXY_YOUTUBE', 'http://host.docker.internal:7897')
    assert proxy_for(config, 'youtube') == 'http://host.docker.internal:7897'


@pytest.mark.parametrize('value', ['socks5://host:1080','http://host:bad','http://host:0','http://host/path','secret','https://host?secret=1'])
def test_invalid_proxy_rejected_without_echoing_credentials(value):
    with pytest.raises(ValueError) as error:
        validate_proxy(value)
    assert value not in str(error.value)
