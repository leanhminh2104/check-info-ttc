import requests, re, json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from http.server import BaseHTTPRequestHandler

# ---------- CONFIG ----------
BASE = "https://tuongtaccheo.com"
LOGIN_PAGE = urljoin(BASE, "/login")
COMMON_LOGIN_POSTS = [urljoin(BASE, "/login"), urljoin(BASE, "/login.php")]
PROFILE_PATHS = ["/profile.php", "/profile", "/home.php", "/dashboard.php", "/"]
MAX_TOKEN_ATTEMPTS = 5
# ----------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 11; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}

HEX_TOKEN_RE = re.compile(r'\b([A-Fa-f0-9]{20,64})\b')
SODU_RE = re.compile(r'"sodu"\s*[:=]\s*["\']?([0-9,\.]+)["\']?', re.I)
SODU_TEXT_RE = re.compile(r'(?:số\s*dư|sodu|xu)[^\d]{0,10}([0-9\.,]{2,})', re.I)


def safe_get(s, url, **kw):
    try:
        return s.get(url, timeout=15, **kw)
    except:
        return None


def safe_post(s, url, data=None, **kw):
    try:
        return s.post(url, data=data, timeout=15, **kw)
    except:
        return None


def parse_login_form(html, base_url):
    soup = BeautifulSoup(html or "", "html.parser")
    form = soup.find("form")
    if not form:
        return None
    action = urljoin(base_url, form.get("action") or "")
    inputs, user_field, pass_field = {}, None, None
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        t = (inp.get("type") or "").lower()
        if t == "password":
            pass_field = name
        elif t in ("text", "email"):
            user_field = user_field or name
        inputs[name] = inp.get("value") or ""
    return {
        "action_url": action,
        "inputs": inputs,
        "user_field": user_field or "username",
        "pass_field": pass_field or "password",
    }


def find_sodu_and_tokens(text):
    out = {}
    if not text:
        return out
    m = SODU_RE.search(text) or SODU_TEXT_RE.search(text)
    if m:
        out["sodu"] = m.group(1)
    hexes = HEX_TOKEN_RE.findall(text)
    if hexes:
        out["hex_like"] = hexes
    return out


def login_with_credentials(s, u, p):
    r = safe_get(s, LOGIN_PAGE)
    parsed = parse_login_form(r.text, LOGIN_PAGE) if r else None
    if parsed:
        payload = parsed["inputs"].copy()
        payload[parsed["user_field"]] = u
        payload[parsed["pass_field"]] = p
        return safe_post(s, parsed["action_url"], data=payload)
    for url in COMMON_LOGIN_POSTS:
        r2 = safe_post(s, url, data={"username": u, "password": p})
        if r2:
            return r2
    return None


def get_profile_info(s):
    accum, pages = {}, {}
    for p in PROFILE_PATHS:
        r = safe_get(s, urljoin(BASE, p))
        if not r:
            continue
        pages[p] = r.status_code
        f = find_sodu_and_tokens(r.text)
        for k, v in f.items():
            if k not in accum:
                accum[k] = v
            elif isinstance(accum[k], list):
                accum[k].extend(v)
    accum["pages"] = pages
    return accum


def try_token(s, tk):
    r = safe_post(s, urljoin(BASE, "/logintoken.php"), data={"access_token": tk})
    if not r:
        return None
    try:
        return r.json()
    except:
        return {"raw": r.text}


def attempt_tokens(s, tokens):
    if not tokens:
        return None
    tried = set()
    for tk in tokens[:MAX_TOKEN_ATTEMPTS]:
        if not tk or tk in tried:
            continue
        tried.add(tk)
        res = try_token(s, tk)
        if res and res.get("status") == "success":
            return {"token": tk, "response": res}
    return None


# ========== Vercel API Handler ==========
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        username = qs.get("username", [None])[0]
        password = qs.get("password", [None])[0]

        if not username or not password:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "username & password required"}).encode()
            )
            return

        s = requests.Session()
        s.headers.update(HEADERS)

        rpost = login_with_credentials(s, username, password)
        found = find_sodu_and_tokens(rpost.text) if rpost else {}
        profile_info = get_profile_info(s)
        for k, v in profile_info.items():
            if k == "pages":
                continue
            found.setdefault(k, v)

        tokens = sorted(set(found.get("hex_like", [])), key=len, reverse=True)
        token_result = attempt_tokens(s, tokens)

        out = {
            "co_token": False,
            "token": None,
            "use": username,
            "mk": password,
            "user": None,
            "sodu": found.get("sodu"),
            "pages": profile_info.get("pages", {}),
        }

        if token_result:
            tk, res = token_result["token"], token_result["response"]
            out.update({"co_token": True, "token": tk})
            if res.get("data"):
                out["user"] = res["data"].get("user")
                out["sodu"] = res["data"].get("sodu")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(out, ensure_ascii=False).encode())
