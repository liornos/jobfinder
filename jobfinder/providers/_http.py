import json
import ssl
import logging
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)
ctx = ssl.create_default_context()

class NotFoundError(Exception):
    pass

def get_json(url: str, timeout=3):
    req = Request(url)
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.load(resp)
    except HTTPError as e:
        if e.code == 404:
            logger.warning("404 Not Found: %s", url)
            raise NotFoundError(f"404: %url")
        else:
            logger.error("HTTPError (%s): %s", e.code, url)
            raise
    except URLError as e:
        logger.error("URLError: %s -> %s", url, e)
        raise