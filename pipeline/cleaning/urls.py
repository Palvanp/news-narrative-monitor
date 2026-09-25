from urllib.parse import parse_qsl, urlencode, urlsplit

TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src", "cmpid", "ito", "src"}
HOST_PREFIXES = ("www.", "m.", "amp.")


def normalize_url(url: str) -> str:
    """Canonical form used for exact-URL dedup: host + path + meaningful query, no scheme.

    Drops www./m./amp. host prefixes, AMP path segments, tracking parameters,
    fragments and trailing slashes, so the same article reached via different
    links compares equal.
    """
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    for prefix in HOST_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix):]

    segments = [s for s in parts.path.split("/") if s and s.lower() != "amp"]
    path = "/" + "/".join(segments) if segments else ""
    if path.lower().endswith((".amp", "/amp.html")):
        path = path.rsplit(".", 1)[0]

    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    query.sort()
    qs = f"?{urlencode(query)}" if query else ""
    return f"{host}{path}{qs}"
