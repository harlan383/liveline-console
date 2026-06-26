from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


VLESS_URL_PREFIX = "vless" + "://"


def is_vless_share_link(share_link: str | None) -> bool:
    return bool(share_link and share_link.startswith(VLESS_URL_PREFIX))


def ensure_vless_tcp_header_type_none(share_link: str) -> str:
    """Return a client-link compatible VLESS URL without mutating stored data."""
    parsed = urlsplit(share_link)
    if parsed.scheme.lower() != "vless" or not parsed.query:
        return share_link

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    lowered_keys = {key.lower() for key, _value in query_items}
    if "headertype" in lowered_keys:
        return share_link

    query_items.append(("headerType", "none"))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query_items), parsed.fragment))
