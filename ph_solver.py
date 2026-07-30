"""Solve pornhub's JS bot-challenge cookie.

The challenge HTML defines:
    var p = <num>; var s = <num>;
    if ((s >> K) & 1) p [+/-]= EXPR; else p [+/-]= EXPR;   (repeated)
    p [+/-]= NUM;
    n = leastFactor(p);
    document.cookie = "KEY=" + n + "*" + p/n + ":" + s + ":<CONST>:1; ..."

We replicate the arithmetic, return cookie string, then re-fetch with it.
"""
import re
import urllib.request
from http.cookiejar import CookieJar

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


def least_factor(n: int) -> int:
    if n == 0:
        return 0
    if n < 2:
        return 1
    if n % 2 == 0:
        return 2
    if n % 3 == 0:
        return 3
    if n % 5 == 0:
        return 5
    m = int(n ** 0.5) + 1
    i = 7
    while i <= m:
        for off in (0, 4, 6, 10, 12, 16, 22, 24):
            if n % (i + off) == 0:
                return i + off
        i += 30
    return n


def strip_js_comments(js: str) -> str:
    js = re.sub(r'/\*.*?\*/', ' ', js, flags=re.DOTALL)
    js = re.sub(r'//[^\n]*', ' ', js)
    return js


# Match arithmetic of literal integers possibly multiplied: "123", "123*45", "1*2*3"
NUM_EXPR = r'(\d+(?:\s*\*\s*\d+)*)'


def eval_int_expr(expr: str) -> int:
    # Safe: only digits and '*' allowed
    parts = [int(x) for x in re.split(r'\s*\*\s*', expr.strip())]
    out = 1
    for p in parts:
        out *= p
    return out


def solve_challenge(html: str) -> str | None:
    """Return cookie string 'KEY=...' or None if challenge not present."""
    js = strip_js_comments(html)
    m = re.search(r'var\s+p\s*=\s*(\d+)\s*;\s*var\s+s\s*=\s*(\d+)\s*;', js)
    if not m:
        return None
    p = int(m.group(1))
    s = int(m.group(2))

    # Find all if/else blocks. Pattern is consistent in challenge JS.
    if_re = re.compile(
        r'if\s*\(\s*\(\s*s\s*>>\s*(\d+)\s*\)\s*&\s*1\s*\)\s*'
        r'p\s*([+-])=\s*' + NUM_EXPR + r'\s*;\s*'
        r'else\s+p\s*([+-])=\s*' + NUM_EXPR + r'\s*;'
    )
    blocks = list(if_re.finditer(js))
    if not blocks:
        return None
    for m in blocks:
        bit = int(m.group(1))
        op_if, expr_if = m.group(2), m.group(3)
        op_else, expr_else = m.group(4), m.group(5)
        if (s >> bit) & 1:
            v = eval_int_expr(expr_if)
            p = p + v if op_if == '+' else p - v
        else:
            v = eval_int_expr(expr_else)
            p = p + v if op_else == '+' else p - v

    # Final adjustment p [+-]= NUM (just before n=leastFactor)
    m = re.search(
        r'p\s*([+-])=\s*' + NUM_EXPR + r'\s*;\s*n\s*=\s*leastFactor\s*\(\s*p\s*\)',
        js,
    )
    if m:
        op, expr = m.group(1), m.group(2)
        v = eval_int_expr(expr)
        p = p + v if op == '+' else p - v

    n = least_factor(p)
    if n == 0:
        return None
    # Cookie format: "KEY="+n+"*"+p/n+":"+s+":<CONST>:1"
    m = re.search(
        r'document\.cookie\s*=\s*"KEY="\s*\+\s*n\s*\+\s*"\*"\s*\+\s*p\s*/\s*n\s*'
        r'\+\s*":"\s*\+\s*s\s*\+\s*":(\d+):',
        js,
    )
    if not m:
        return None
    const = m.group(1)
    return f'KEY={n}*{p // n}:{s}:{const}:1'


def _add_cookie(cj: CookieJar, name: str, value: str, domain: str):
    from http.cookiejar import Cookie
    cj.set_cookie(Cookie(
        version=0, name=name, value=value, port=None, port_specified=False,
        domain=domain, domain_specified=True, domain_initial_dot=domain.startswith('.'),
        path='/', path_specified=True, secure=False, expires=None,
        discard=True, comment=None, comment_url=None, rest={}, rfc2109=False,
    ))


def fetch_with_challenge(url: str, timeout: int = 15) -> str | None:
    """Fetch URL, solving challenge if encountered. Return final HTML or None.

    Uses a per-call CookieJar so the server's other Set-Cookie values
    (ua, platform, sessid, etc.) are preserved alongside the solved KEY.
    """
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ('User-Agent', UA),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
        ('Accept-Language', 'en-US,en;q=0.9'),
    ]
    try:
        for _ in range(3):
            r = opener.open(url, timeout=timeout)
            body = r.read(524288).decode('utf-8', errors='replace')
            if 'leastFactor' not in body:
                return body  # real content
            cookie = solve_challenge(body)
            if not cookie:
                return None
            name, value = cookie.split('=', 1)
            # The cookie domain in the JS is path=/ (no domain) — applies to current host.
            host = urllib.parse.urlparse(url).hostname or ''
            _add_cookie(cj, name, value, host)
        return None
    except Exception:
        return None


import urllib.parse  # noqa: E402  (used above)


if __name__ == '__main__':
    # Self-test
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else \
        'https://www.pornhub.com/view_video.php?viewkey=ph627d44e7372ca'
    body = fetch_with_challenge(test_url)
    if body is None:
        print('Failed')
    else:
        m = re.search(
            r'<meta[^>]+og:image[^>]+content=["\']([^"\']+)', body, re.I
        )
        m2 = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*og:image', body, re.I
        )
        m = m or m2
        print('og:image =', m.group(1) if m else '(not found)')
        print('len=', len(body))
