"""把本地资料逐篇整理成详情记录与注音记录，原始文本落盘以便重复解析。

用全局令牌桶控制处理节奏；遇到对方的速率提示时整体降速并退避等待，
已处理过的文件直接跳过，可以随时中断续跑。

输入目录与数据源地址分别由 RAW_DIR / SOURCE_BASE 环境变量给出，
仓库里不预设任何具体站点。
"""
import json
import os
import sys
import threading
import time
import http.cookiejar
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("RAW_DIR") or (ROOT / "raw"))
OUT = ROOT / "data"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HOST = (os.environ.get("SOURCE_BASE") or "").rstrip("/")
WORKERS = 3
BASE_INTERVAL = 0.62

_lock = threading.Lock()
_stat = {"detail": 0, "pinyin": 0, "skip": 0, "fail": 0, "throttle": 0}
_rate = {"interval": BASE_INTERVAL, "next": 0.0}

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def acquire() -> None:
    """全局串行化请求节奏。"""
    while True:
        with _lock:
            now = time.time()
            if now >= _rate["next"]:
                _rate["next"] = max(now, _rate["next"]) + _rate["interval"]
                return
            wait = _rate["next"] - now
        time.sleep(min(wait, 0.4))


def fetch(url: str, referer: str = None) -> str:
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    for attempt in range(8):
        acquire()
        try:
            req = urllib.request.Request(url, headers=headers)
            with _opener.open(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (512, 429, 403):
                with _lock:
                    _stat["throttle"] += 1
                    _rate["interval"] = min(_rate["interval"] * 1.35, 3.0)
                time.sleep(12 + 8 * attempt + random.random() * 3)
                continue
            time.sleep(2 + attempt)
        except Exception:
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"give up: {url}")


def recover_rate() -> None:
    with _lock:
        if _rate["interval"] > BASE_INTERVAL:
            _rate["interval"] = max(BASE_INTERVAL, _rate["interval"] * 0.97)


def bump(key: str) -> None:
    with _lock:
        _stat[key] += 1


def save(path: Path, text: str) -> None:
    tmp = Path(str(path) + ".part")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def work(entry: dict) -> None:
    pid = entry["id"]
    detail, pinyin = RAW / f"{pid}.html", RAW / f"{pid}.yin.html"
    url = f"{HOST}/shiwenv_{pid}.aspx"
    try:
        if detail.exists() and detail.stat().st_size > 800:
            bump("skip")
        else:
            html = fetch(url, referer=f"{HOST}/gushi/")
            if "未找到对应诗文" in html or "contson" not in html:
                save(detail, "")
                bump("fail")
                return
            save(detail, html)
            bump("detail")
        if not pinyin.exists():
            ajax = f"{HOST}/nocdn/ajaxshiwenDetailCont.aspx?id={pid}&value=yin"
            save(pinyin, fetch(ajax, referer=url))
            bump("pinyin")
        recover_rate()
    except Exception as exc:
        bump("fail")
        with _lock:
            with open(OUT / "errors.log", "a", encoding="utf-8") as fh:
                fh.write(f"{pid}\t{type(exc).__name__}\t{exc}\n")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    entries = json.loads((OUT / "catalog.json").read_text(encoding="utf-8"))["poems"]
    def missing(e):
        d, p = RAW / f"{e['id']}.html", RAW / f"{e['id']}.yin.html"
        return not (d.exists() and d.stat().st_size > 800) or not p.exists()

    todo = [e for e in entries if missing(e)]
    print(f"total={len(entries)} to_fetch={len(todo)}", flush=True)
    start = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, _ in enumerate(pool.map(work, todo), 1):
            if i % 40 == 0:
                rate = i / max(time.time() - start, 1)
                left = (len(todo) - i) / max(rate, 0.01) / 60
                print(
                    f"{i}/{len(todo)} {_stat} int={_rate['interval']:.2f}s "
                    f"{rate:.2f}poem/s eta{left:.0f}m",
                    flush=True,
                )
    print("done", _stat, f"{time.time() - start:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
