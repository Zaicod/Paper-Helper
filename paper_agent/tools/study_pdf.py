"""Bounded public HTTPS PDF loading with DNS pinning on every redirect."""
from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import ssl
import time
from io import BytesIO
from urllib.parse import urljoin, urlsplit

from paper_agent.core.models import EvidenceChunk, Paper

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PAGES = 200
MAX_TEXT_CHARS = 2_000_000


class PDFDownloadError(ValueError):
    def __init__(self,status):
        super().__init__('PDF source did not return accessible content')
        self.preparation_status='blocked' if status in (401,403) else 'unavailable'


def _public_target(url: str) -> tuple[str, str, str]:
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.port not in (None, 443)
            or len(url) > 2048 or any(ord(c) < 32 for c in url)):
        raise ValueError('Only public HTTPS PDF URLs are supported')
    host = parts.hostname.encode('idna').decode('ascii')
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('PDF address must resolve only to public IP addresses')
    target = parts.path or '/'
    if parts.query:
        target += '?' + parts.query
    return host, addresses[0][4][0], target


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the validated numeric address; preserve the host for TLS SNI
        # and certificate validation. No second DNS lookup can rebind to localhost.
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _fetch_public_pdf(url: str) -> tuple[bytes, str]:
    deadline = time.monotonic() + 60
    for _ in range(6):
        host, address, target = _public_target(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('PDF download deadline exceeded')
        connection = _PinnedHTTPSConnection(host, address, min(10, remaining))
        try:
            connection.request('GET', target, headers={'Accept': 'application/pdf',
                'User-Agent': 'PaperFlow-study/0.3', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('PDF redirect has no location')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise PDFDownloadError(response.status)
            length = response.getheader('Content-Length')
            if length and (not length.isdigit() or int(length) > MAX_PDF_BYTES):
                raise ValueError('PDF exceeds download limit')
            content = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError('PDF download deadline exceeded')
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > MAX_PDF_BYTES:
                    raise ValueError('PDF exceeds download limit')
            if not content.lstrip().startswith(b'%PDF-'):
                raise ValueError('Downloaded content is not a PDF')
            return bytes(content), url
        finally:
            connection.close()
    raise ValueError('Too many PDF redirects')


def _extract_pdf(content: bytes, paper: Paper, source_url: str) -> list[EvidenceChunk]:
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
        raise ValueError('Encrypted PDF or unsupported page count')
    chunks = []
    total = 0
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or '').strip()
        total += len(text)
        if total > MAX_TEXT_CHARS:
            raise ValueError('PDF text exceeds processing limit')
        for index, start in enumerate(range(0, len(text), 3600)):
            part = text[start:start+4000]
            if part.strip():
                chunks.append(EvidenceChunk(chunk_id=f'{paper.paper_id}:p{number}:{index}',
                    paper_id=paper.paper_id, text=part, page_number=number, source_url=source_url))
    if total < 300:
        raise ValueError('PDF has insufficient readable text; OCR is not supported')
    return chunks


class StudyPDFLoader:
    async def load(self, paper: Paper) -> list[EvidenceChunk]:
        if not paper.pdf_url:
            raise ValueError('Paper has no open PDF URL')
        url = paper.pdf_url
        parts = urlsplit(url)
        # arXiv's official Atom API still emits canonical HTTP PDF links.
        # Upgrade that exact authority only; arbitrary HTTP links remain denied.
        if (parts.scheme == 'http' and parts.netloc.lower() == 'arxiv.org'
                and parts.path.startswith('/pdf/')):
            url = parts._replace(scheme='https').geturl()
        async with asyncio.timeout(90):
            content, source = await asyncio.to_thread(_fetch_public_pdf, url)
            return await asyncio.to_thread(_extract_pdf, content, paper, source)
