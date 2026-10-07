"""采集合集目录，生成待整理明细 id 清单。

数据源地址由 SOURCE_BASE 环境变量给出（默认 example.invalid），
请只对你**有权访问**的资料使用本脚本。
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("RAW_DIR") or (ROOT / "raw"))
OUT = ROOT / "data"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE = (os.environ.get("SOURCE_BASE") or "https://example.invalid").rstrip("/")

# 合集目录页 -> 中文名称
CATEGORIES = {
    "tangshi": "唐诗三百首",
    "songci": "宋词精选",
    "sanbai": "古诗三百首",
    "shijing": "诗经",
    "chuci": "楚辞",
    "yuefu": "乐府",
    "shijiu": "古诗十九首",
    "wanyue": "婉约词",
    "haofang": "豪放词",
    "xiaoxue": "小学古诗文",
    "chuzhong": "初中古诗文",
    "gaozhong": "高中古诗文",
}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    index = {}
    for slug, name in CATEGORIES.items():
        cache = RAW / f"cat_{slug}.html"
        html = cache.read_text(encoding="utf-8", errors="replace") if cache.exists() else ""
        if not html:
            html = get(f"{BASE}/gushi/{slug}.aspx")
            cache.write_text(html, encoding="utf-8")
        ids = re.findall(r"/shiwenv_([a-z0-9]{12})\.aspx", html)
        for pid in dict.fromkeys(ids):
            e = index.setdefault(pid, {"id": pid, "cats": []})
            e["cats"].append(name)
        print(f"{name}: {len(ids)}", flush=True)
    payload = {
        "categories": [{"slug": s, "name": n} for s, n in CATEGORIES.items()],
        "poems": sorted(index.values(), key=lambda x: x["id"]),
    }
    (OUT / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    print("unique poems:", len(index))
    return 0


if __name__ == "__main__":
    sys.exit(main())
