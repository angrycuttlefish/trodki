"""trodki: Interactive Brokers Flex Web Service client.

A Flex query is set up once by the user in Client Portal. Its statement is fetched in two
steps: `SendRequest` with the token and the query id returns a reference code and the URL to
poll, then `GetStatement` with the reference code returns the statement once it is generated.
https://www.interactivebrokers.com/docs/web-api/flex-web-service/flex-web-service/introduction
"""
import logging
from typing import Final
from urllib.parse import urlparse
from xml.etree.ElementTree import Element, ParseError  # noqa: S405  # types only, parsing is defusedxml

import requests
from defusedxml import DefusedXmlException, ElementTree

from rotkehlchen.concurrency import cancellable_sleep
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.utils.network import create_session

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

FLEX_SEND_REQUEST_URL: Final = 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest'
FLEX_API_VERSION: Final = '3'
FLEX_STATEMENT_IN_PROGRESS: Final = '1019'
IN_PROGRESS_BACKOFF_SECONDS: Final = (5, 10, 20)


class FlexWebService:

    def __init__(self, token: str, query_id: str, session: requests.Session | None = None) -> None:
        self.token = token
        self.query_id = query_id
        self.session = session if session is not None else create_session()

    def _get(self, url: str, reference: str) -> bytes:
        """May raise RemoteError"""
        try:
            response = self.session.get(
                url=url,
                params={'t': self.token, 'q': reference, 'v': FLEX_API_VERSION},
                timeout=CachedSettings().get_timeout_tuple(),
            )
        except requests.RequestException as e:
            msg = str(e).replace(self.token, '***') if self.token else str(e)
            raise RemoteError(f'IBKR Flex request failed: {msg}') from e
        if response.status_code != 200:
            raise RemoteError(f'IBKR Flex returned HTTP {response.status_code}: {response.text[:200]}')  # noqa: E501
        return response.content

    def _send_request(self) -> tuple[str, str]:
        """Returns the reference code and the URL to fetch the statement from.

        May raise RemoteError
        """
        root = _parse(self._get(FLEX_SEND_REQUEST_URL, self.query_id))
        _raise_on_error(root)
        reference, url = root.findtext('ReferenceCode'), root.findtext('Url')
        if not reference or not url:
            raise RemoteError(f'Unexpected IBKR Flex SendRequest response: {ElementTree.tostring(root)[:200]!r}')  # noqa: E501
        clean_url = url.strip()
        parsed = urlparse(clean_url)
        hostname = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or not (hostname == 'interactivebrokers.com' or hostname.endswith('.interactivebrokers.com')):  # noqa: E501
            raise RemoteError(f'Unexpected IBKR Flex statement URL: {clean_url!r}')
        return reference.strip(), clean_url

    def validate(self) -> tuple[bool, str]:
        """Check the token and query id by asking IBKR to generate the statement"""
        try:
            self._send_request()
        except RemoteError as e:
            return False, str(e)
        return True, ''

    def fetch_statement(self) -> bytes:
        """The raw statement of the user's Flex query.

        May raise RemoteError
        """
        reference, url = self._send_request()
        for backoff in (*IN_PROGRESS_BACKOFF_SECONDS, None):
            raw = self._get(url, reference)
            root = _parse(raw)
            if root.tag != 'FlexStatementResponse':
                return raw
            if root.findtext('ErrorCode') != FLEX_STATEMENT_IN_PROGRESS:
                _raise_on_error(root)
                raise RemoteError(f'Unexpected IBKR Flex GetStatement response: {raw[:200]!r}')
            if backoff is None:
                break
            log.debug(f'IBKR Flex statement {reference} is being generated, retrying in {backoff}s')  # noqa: E501
            cancellable_sleep(backoff)

        raise RemoteError('IBKR Flex statement is still being generated. Try again later')


def _parse(raw: bytes) -> Element:
    """May raise RemoteError"""
    try:
        return ElementTree.fromstring(raw)
    except (ParseError, DefusedXmlException) as e:
        raise RemoteError(f'IBKR Flex returned malformed XML: {e!s}') from e


def _raise_on_error(root: Element) -> None:
    """May raise RemoteError with IBKR's error code and message"""
    if root.tag == 'FlexStatementResponse' and (code := root.findtext('ErrorCode')) is not None:
        message = (root.findtext('ErrorMessage') or '').strip()
        raise RemoteError(f'IBKR Flex error {code.strip()}: {message}')
