'''
The app's version, and the check for a newer one on GitHub Releases (shown as a banner in the dashboard).
Bump APP_VERSION (and AppVersion in packaging/installer.iss) for every release, tagged "v<version>" on GitHub.
'''

import json
import time
import urllib.request

APP_VERSION = "2.1.0"
REPO = "saif-siddiqui06/Apply-and-Pray"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
_cache: dict = {"at": 0.0, "result": None}


def _parts(version: str) -> tuple:
    return tuple(int(part) for part in __import__("re").findall(r'\d+', version or "")[:3]) or (0,)


def latest_release(max_age: float = 6 * 3600) -> dict:
    '''{"current", "latest", "newer": bool, "url", "notes"}; never raises (no internet = no banner).'''
    if _cache["result"] and time.time() - _cache["at"] < max_age: return _cache["result"]
    result = {"current": APP_VERSION, "latest": APP_VERSION, "newer": False, "url": RELEASES_PAGE, "notes": ""}
    try:
        request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                         headers={"Accept": "application/vnd.github+json", "User-Agent": "Apply-and-Pray"})
        with urllib.request.urlopen(request, timeout=8) as response: data = json.loads(response.read().decode("utf-8"))
        latest = (data.get("tag_name") or "").lstrip("v")
        result.update(latest=latest or APP_VERSION, newer=bool(latest) and _parts(latest) > _parts(APP_VERSION),
                      url=data.get("html_url") or RELEASES_PAGE, notes=(data.get("body") or "")[:400])
    except Exception:
        pass
    _cache.update(at=time.time(), result=result)
    return result
