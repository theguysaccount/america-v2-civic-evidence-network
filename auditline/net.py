"""One polite download: robots.txt first, an honest User-Agent, a size limit, and no workarounds.

- If the publisher's robots.txt disallows the address, or the publisher answers 401, 403, 406 or 429,
  that is a refusal. It is reported as a refusal and nothing else is tried.
- One thing is repaired: a server that sends an incomplete certificate chain. Browsers fix that by
  fetching the missing issuer certificate named in the site's own certificate, and so does this.
  The completed chain must still end at a root this machine already trusts.
"""
import re
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .robots import from_response


class Refused(Exception):
    """The publisher declined an automated request (robots.txt, 401/403/406/429, or a bot check)."""


class Unreachable(Exception):
    """No usable answer (network, TLS, 5xx, wrong content type, too large)."""


def _issuer_pem(host, timeout=20):
    """Read the server certificate's 'CA Issuers' address and fetch that issuer certificate."""
    probe = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    probe.check_hostname = False
    probe.verify_mode = ssl.CERT_NONE          # only to read the certificate; no request is sent on this socket
    with socket.create_connection((host, 443), timeout=timeout) as sock:
        with probe.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    m = re.search(rb"http://[\x21-\x7e]{6,200}?\.(?:crt|cer)", der or b"")
    if not m:
        return None
    with urllib.request.urlopen(m.group(0).decode("ascii"), timeout=timeout) as r:
        blob = r.read(60_000)
    return blob.decode("ascii") if blob.lstrip().startswith(b"-----BEGIN") else ssl.DER_cert_to_PEM_cert(blob)


def _context_with_issuer(host):
    pem = _issuer_pem(host)
    if not pem:
        return None
    ctx = ssl.create_default_context()
    flag = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    if flag:
        ctx.verify_flags &= ~flag               # the chain must still reach a trusted root
    ctx.load_verify_locations(cadata=pem)
    return ctx


def _open(url, headers, timeout, context=None):
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout, context=context)


def get(url, ua, accept, max_bytes, timeout=120, trusted_hosts=None):
    """Return (bytes, headers) or raise Refused / Unreachable. Redirects must stay on the publisher's hosts."""
    host = urlsplit(url).hostname or ""
    headers = {"User-Agent": ua, "Accept": accept}
    context = None
    for attempt in range(2):
        try:
            with _open(url, headers, timeout, context) as r:
                final = urlsplit(r.geturl()).hostname or ""
                if trusted_hosts and final not in trusted_hosts:
                    raise Unreachable(f"redirected to {final}, which is not one of the publisher's hosts")
                body = r.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise Unreachable(f"larger than {max_bytes:,} bytes")
                return body, {k.lower(): v for k, v in r.headers.items()}, r.status
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 406, 429):
                raise Refused(f"HTTP {e.code}")
            return b"", {}, e.code
        except urllib.error.URLError as e:
            reason = str(getattr(e, "reason", e))
            if attempt == 0 and "CERTIFICATE_VERIFY_FAILED" in reason and "unable to get local issuer" in reason:
                try:
                    context = _context_with_issuer(host)
                except Exception:
                    context = None
                if context is not None:
                    continue
            raise Unreachable(reason[:160])
        except (OSError, ssl.SSLError) as e:
            raise Unreachable(f"{type(e).__name__}: {e}"[:160])
    raise Unreachable("certificate chain could not be completed")


def fetch_export(source, cfg):
    """robots.txt, then the export. Returns (bytes, headers)."""
    ua = cfg["user_agent"]
    parts = urlsplit(source["url"])
    try:
        body, _, status = get(f"{parts.scheme}://{parts.hostname}/robots.txt", ua, "text/plain,*/*;q=0.5", 500_000, timeout=40)
    except Refused as e:
        raise Refused(f"robots.txt: {e}")
    if status not in (200, 404, 410):
        raise Unreachable(f"robots.txt answered HTTP {status}")      # a server error is not a refusal: try again later
    rules, note = from_response(status, body.decode("utf-8", "replace") if status == 200 else "")
    if status == 200 and b"<html" in body[:2000].lower():
        raise Refused("robots.txt answered with a web page (a bot check)")
    if not rules.allowed(source["url"], cfg["robots_token"]):
        raise Refused(f"robots.txt disallows this address ({note})")
    body, headers, status = get(source["url"], ua, "text/csv,text/plain;q=0.9", cfg["max_bytes"], trusted_hosts=source["hosts"])
    if status != 200:
        raise Unreachable(f"HTTP {status}")
    ctype = headers.get("content-type", "")
    if "html" in ctype.lower() or body[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        raise Refused("answered with a web page instead of the export (a bot check)")
    return body, headers
