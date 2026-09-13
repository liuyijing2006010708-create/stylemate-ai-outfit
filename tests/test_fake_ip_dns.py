import httpcore
import httpx
import pytest

from stylemate.security import PublicBackend, UnsafeURL, resolve_public


def install_dns(monkeypatch, answers=None, handler=None):
    """Mock only the two external boundaries: OS DNS and HTTPS DNS."""
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("198.18.0.49", 443))])
    client_class = httpx.Client
    seen = []

    def respond(request):
        seen.append(request)
        if handler:
            return handler(request)
        kind = int(request.url.params["type"])
        return httpx.Response(200, json={
            "Status": 0, "Question": [{"name": "relay.example.", "type": kind}],
            "Answer": [{"type": kind, "data": ip} for ip in
                       (answers if answers is not None else ["8.8.8.8"])
                       if (":" in ip) == (kind == 28)]})

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs.get("verify", True) is True
        return client_class(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr("stylemate.security.httpx.Client", client)
    return seen


def test_fake_ip_resolves_and_connects_to_verified_public_ip(monkeypatch):
    seen = install_dns(monkeypatch)
    connected = []
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp",
                        lambda self, host, *a: connected.append(host))
    PublicBackend().connect_tcp("relay.example", 443)
    assert connected == ["8.8.8.8"]
    assert len(seen) == 2
    for request in seen:
        assert request.url.host == "1.1.1.1"
        assert request.url.path == "/dns-query"
        assert request.url.params["name"] == "relay.example"
        assert "authorization" not in request.headers
        assert request.content == b""


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254",
    "198.19.0.5", "::1", "::ffff:127.0.0.1", "64:ff9b::7f00:1"])
def test_doh_private_or_mixed_answers_still_blocked(monkeypatch, ip):
    install_dns(monkeypatch, ["8.8.8.8", ip])
    with pytest.raises(UnsafeURL):
        resolve_public("relay.example", 443)


@pytest.mark.parametrize("payload", [{}, {"Status": 3}, {"Status": 0, "Answer": []},
    {"Status": 0, "Question": [{"name": "wrong.example", "type": 1}]},
    {"Status": 0, "Answer": [{"type": 1, "data": "not-an-ip"}]}])
def test_bad_doh_response_fails_closed(monkeypatch, payload):
    install_dns(monkeypatch, handler=lambda r: httpx.Response(200, json=payload))
    with pytest.raises(UnsafeURL):
        resolve_public("relay.example", 443)


@pytest.mark.parametrize("code", [302, 500])
def test_doh_does_not_follow_redirects_or_accept_server_errors(monkeypatch, code):
    seen = install_dns(monkeypatch, handler=lambda r: httpx.Response(
        code, headers={"Location": "https://127.0.0.1/"}))
    with pytest.raises(UnsafeURL):
        resolve_public("relay.example", 443)
    assert len(seen) == 1


def test_fake_ip_mixed_with_private_os_dns_does_not_query_doh(monkeypatch):
    seen = install_dns(monkeypatch)
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", (ip, 443)) for ip in ["198.18.0.49", "127.0.0.1"]])
    with pytest.raises(UnsafeURL):
        resolve_public("relay.example", 443)
    assert seen == []


def test_normal_public_dns_does_not_query_doh(monkeypatch):
    seen = install_dns(monkeypatch)
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("8.8.4.4", 443))])
    assert resolve_public("relay.example", 443) == "8.8.4.4"
    assert seen == []


def test_literal_fake_ip_is_not_reinterpreted_as_hostname(monkeypatch):
    seen = install_dns(monkeypatch)
    with pytest.raises(UnsafeURL):
        resolve_public("198.18.0.49", 443)
    assert seen == []


def test_doh_response_size_is_bounded(monkeypatch):
    seen = install_dns(monkeypatch, handler=lambda r: httpx.Response(200, content=b" " * 70000))
    with pytest.raises(UnsafeURL) as error:
        resolve_public("relay.example", 443)
    assert error.value.reason == "fake_ip"
    assert len(seen) == 1


def test_doh_timeout_fails_without_connecting_to_fake_ip(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("private DNS detail")
    seen = install_dns(monkeypatch, handler=timeout)
    with pytest.raises(UnsafeURL) as error:
        resolve_public("relay.example", 443)
    assert error.value.reason == "fake_ip"
    assert "private" not in str(error.value)
    assert len(seen) == 1
