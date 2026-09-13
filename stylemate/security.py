"""Outbound requests resolve and connect only to public addresses."""

import ipaddress
import json
import logging
import socket
from urllib.parse import urlsplit

import httpcore
import httpx


class UnsafeURL(ValueError):
    def __init__(self, message, *, reason="unsafe_url"):
        super().__init__(message)
        self.reason = reason


def validate_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
        if (parts.scheme != "https" or not host or parts.username or parts.password
                or parts.fragment or not 1 <= (parts.port or 443) <= 65535
                or any(ord(c) < 33 for c in url) or "\\" in url):
            raise ValueError
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not public_address(address):
            raise ValueError
    except ValueError:
        raise UnsafeURL("地址不安全：仅允许 HTTPS 公网地址，禁止本机、内网和保留地址。") from None
    return host


def public_address(address):
    # Block IPv6 transition addresses as well as ordinary private ranges.
    return (address.is_global and not address.is_multicast
            and not getattr(address, "ipv4_mapped", None)
            and not getattr(address, "sixtofour", None)
            and not getattr(address, "teredo", None)
            and not (address.version == 6 and address in ipaddress.ip_network("64:ff9b::/96")))


def resolve_public(host: str, port: int) -> str:
    host = validate_url(f"https://[{host}]" if ":" in host else f"https://{host}")
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise UnsafeURL("无法解析服务地址，请检查域名。", reason="dns_failure") from None
    addresses = [ipaddress.ip_address(record[4][0]) for record in records]
    fake_addresses = [address for address in addresses if address.version == 4
                      and address in ipaddress.ip_network("198.18.0.0/15")]
    # Only Fake-IP may trigger recovery. Never ignore other unsafe OS answers.
    if any(not public_address(address) and address not in fake_addresses
           for address in addresses):
        raise UnsafeURL("地址不安全：域名解析到了非公网地址。", reason="non_public")
    if fake_addresses:
        addresses = resolve_public_doh(host)
    if not addresses or any(not public_address(address) for address in addresses):
        raise UnsafeURL("地址不安全：域名解析到了非公网地址。", reason="non_public")
    return str(addresses[0])


def resolve_public_doh(host: str):
    """Recover Fake-IP via fixed HTTPS DNS; send only the hostname, never API data."""
    addresses = []
    try:
        # Numeric bootstrap avoids resolving the DNS service through Fake-IP.
        # A separate client prevents recursive resolution and credential sharing.
        with httpx.Client(timeout=4.0, trust_env=False, follow_redirects=False,
                          verify=True) as client:
            for kind in (1, 28):
                with client.stream("GET", "https://1.1.1.1/dns-query",
                                   params={"name": host, "type": kind},
                                   headers={"Accept": "application/dns-json"}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise ValueError("DNS response too large")
                data = json.loads(body)
                if data.get("Status") != 0 or data.get("TC"):
                    raise ValueError("DNS query failed")
                questions = data.get("Question", [])
                if (len(questions) != 1 or questions[0].get("type") != kind
                        or questions[0].get("name", "").rstrip(".").lower() != host):
                    raise ValueError("DNS question mismatch")
                for record in data.get("Answer", []):
                    if record.get("type") in (1, 28):
                        address = ipaddress.ip_address(record["data"])
                        if address.version != (4 if record["type"] == 1 else 6):
                            raise ValueError("DNS address type mismatch")
                        addresses.append(address)
        if not addresses:
            raise ValueError("No DNS addresses")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        raise UnsafeURL("Fake-IP 公网解析回退失败。", reason="fake_ip") from None
    # Check every A/AAAA answer, including mixed public/private answers.
    if any(not public_address(address) for address in addresses):
        raise UnsafeURL("地址不安全：公网 DNS 返回非公网地址。", reason="non_public")
    return addresses


class PublicBackend(httpcore.SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        address = resolve_public(host, port)
        # Connect to the numeric address we checked, not a second DNS lookup.
        # HTTPcore retains the original origin for TLS SNI/certificate validation.
        return super().connect_tcp(address, port, timeout, local_address, socket_options)


class PublicTransport(httpx.HTTPTransport):
    def __init__(self):
        super().__init__(retries=0)
        # Adapter point tested against the pinned httpx/httpcore versions.
        self._pool._network_backend = PublicBackend()

    def handle_request(self, request):
        validate_url(str(request.url))
        return super().handle_request(request)


def secure_http_client(**kwargs):
    return httpx.Client(transport=PublicTransport(), follow_redirects=False,
                        trust_env=False, **kwargs)


class DropProviderLogs(logging.Filter):
    def filter(self, record):
        return False


def protect_provider_logs():
    # SDK debug output contains response bodies, headers and signed URLs.
    # Filter descendants too, even if OPENAI_LOG enabled debug before import.
    names = {"openai", "httpx", "httpcore"}
    names.update(name for name in logging.Logger.manager.loggerDict
                 if name.startswith(("openai.", "httpx.", "httpcore.")))
    for name in names:
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL + 1)
        if not any(isinstance(f, DropProviderLogs) for f in logger.filters):
            logger.addFilter(DropProviderLogs())
