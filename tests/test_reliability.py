import logging
from types import SimpleNamespace

import httpcore
import httpx
import pytest

from stylemate.security import PublicBackend, UnsafeURL, validate_url, resolve_public, protect_provider_logs, secure_http_client
from stylemate.operations import OperationGate, BusyError
from stylemate.runtime import APIConfig, safe_connection_error, verify_api_key


@pytest.mark.parametrize("url", ["http://example.com", "https://localhost/v1", "https://localhost./v1",
    "https://127.0.0.1", "https://10.0.0.1", "https://169.254.169.254", "https://[::1]",
    "https://[::ffff:127.0.0.1]", "https://[64:ff9b::7f00:1]", "https://224.0.0.1",
    "https://192.168.0.1", "https://user:secret@example.com", "https://example.com:99999"])
def test_blocks_unsafe_urls(url):
    with pytest.raises(UnsafeURL):
        validate_url(url)


def test_mixed_dns_answers_fail_closed(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(UnsafeURL):
        resolve_public("relay.example", 443)


def test_fake_ip_error_is_actionable_even_through_sdk_wrapper(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("198.18.0.49", 443))])
    def unavailable(**kwargs):
        raise httpx.ConnectError("secret DNS detail")
    monkeypatch.setattr("stylemate.security.httpx.Client", unavailable)
    with pytest.raises(UnsafeURL) as caught:
        resolve_public("relay.example", 443)
    wrapper = RuntimeError("secret provider payload")
    wrapper.__cause__ = caught.value
    message = safe_connection_error(wrapper)
    assert "Fake-IP" in message and "真实" in message
    assert "secret" not in message


def test_dns_failure_has_distinct_actionable_message(monkeypatch):
    import socket
    def fail(*a, **k): raise socket.gaierror("private DNS detail")
    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(UnsafeURL) as caught:
        resolve_public("relay.example", 443)
    assert "DNS" in safe_connection_error(caught.value)
    assert "private" not in safe_connection_error(caught.value)


def test_connect_pins_checked_ip(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    connected = []
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", lambda self, host, *a: connected.append(host))
    PublicBackend().connect_tcp("relay.example", 443)
    assert connected == ["8.8.8.8"]


def test_network_client_disables_proxy_and_redirects(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1111")
    with secure_http_client(timeout=2) as client:
        assert not client.follow_redirects
        assert not client.trust_env
        assert isinstance(client._transport._pool._network_backend, PublicBackend)
        with pytest.raises(UnsafeURL):
            client.get("https://127.0.0.1")


def test_secrets_not_in_repr_errors_or_provider_logs(caplog):
    config = APIConfig.from_values(api_key="my-secret-text", image_api_key="my-secret-image",
        base_url="https://example.com/v1", text_model="vision", image_model="image", text_api="responses")
    assert "my-secret" not in repr(config)
    assert "my-secret" not in safe_connection_error(RuntimeError("my-secret-image"))
    logger = logging.getLogger("openai._base_client")
    protect_provider_logs()
    with caplog.at_level(logging.DEBUG, logger="openai._base_client"):
        logger.error("my-secret-image")
    assert "my-secret" not in caplog.text


def test_gate_blocks_duplicates_shared_keys_and_recovers_after_error():
    now = [0]
    gate = OperationGate(limit=2, cooldown=10, clock=lambda: now[0])
    with gate.claim("a", "secret"):
        with pytest.raises(BusyError):
            with gate.claim("a", "other"): pass
        with pytest.raises(BusyError):
            with gate.claim("b", "secret"): pass
    with pytest.raises(BusyError):
        with gate.claim("b", "secret"): pass
    now[0] = 11
    with pytest.raises(ValueError):
        with gate.claim("a", "secret"): raise ValueError()
    assert not gate.active
    now[0] = 22
    with pytest.raises(BusyError):
        with gate.claim("a", "secret"): pass
    now[0] = 601
    with gate.claim("a", "secret"): pass
    assert "secret" not in repr(gate.history)


@pytest.mark.parametrize("protocol", ["responses", "chat_completions"])
@pytest.mark.parametrize("code", [400, 404, 422])
def test_protocol_errors_never_count_as_verified(protocol, code):
    def reject(**kwargs):
        error = RuntimeError("private response")
        error.status_code = code
        raise error
    fake = SimpleNamespace(responses=SimpleNamespace(create=reject),
                           chat=SimpleNamespace(completions=SimpleNamespace(create=reject)))
    with pytest.raises(RuntimeError):
        verify_api_key("secret", base_url="https://relay.example.com/v1", text_api=protocol,
                       client_factory=lambda **k: fake)
