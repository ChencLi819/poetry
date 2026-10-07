"""量一下各目录的真实规模，用来估算全量采集的代价。

数据源地址由 SOURCE_BASE 环境变量给出（默认 example.invalid），
请只对你**有权访问**的资料使用本脚本。
"""
import os
import re
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = (os.environ.get("SOURCE_BASE") or "https://example.invalid").rstrip("/")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as exc:
        return getattr(exc, "code", 0), ""


def probe_pages(base, id_pat, lo, hi):
    """二分找最大页数（返回能拿到结果的最后一页码）。"""
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        code, html = get(f"{base}{mid}")
        n = len(set(re.findall(id_pat, html))) if code == 200 else -1
        print(f"  page={mid:>6} http={code} items={n}", flush=True)
        if n > 0:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
        time.sleep(2)
    return best


def main():
    code, html = get(f"{BASE}/shiwens/default.aspx")
    print("shiwens page1:", code, "items:",
          len(set(re.findall(r"/shiwenv_([a-z0-9]{12})\.aspx", html))), flush=True)
    if code != 200:
        print("源暂不可达 — 稍后再试")
        return 1
    per = len(set(re.findall(r"/shiwenv_([a-z0-9]{12})\.aspx", html))) or 20

    print("== 诗文目录分页上限 ==")
    last = probe_pages(f"{BASE}/shiwens/default.aspx?page=",
                       r"/shiwenv_([a-z0-9]{12})\.aspx", 2, 4000)
    print(f"=> 约 {last} 页 × {per} ≈ {last * per} 篇诗文", flush=True)

    print("== 作者目录 ==")
    code, html = get(f"{BASE}/authors/default.aspx")
    a_per = len(set(re.findall(r"/authorv_([a-z0-9]{12})\.aspx", html)))
    print("http", code, "每页作者", a_per, flush=True)
    last_a = probe_pages(f"{BASE}/authors/default.aspx?page=",
                         r"/authorv_([a-z0-9]{12})\.aspx", 2, 2000)
    print(f"=> 约 {last_a} 页 × {a_per} ≈ {last_a * a_per} 位作者", flush=True)

    print("== 名句目录 ==")
    code, html = get(f"{BASE}/mingjus/default.aspx")
    print("http", code, "每页名句",
          len(set(re.findall(r"/mingju_([a-z0-9]+)\.aspx", html))), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
