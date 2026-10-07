"""把 raw/ 里的详情页解析成结构化记录（按采集顺序）。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse import parse_detail, parse_pinyin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("RAW_DIR") or (ROOT / "raw"))
OUT = ROOT / "data"


def load_catalog():
    """合集目录页里的归属，用来给其他来源的页面回填标签（那些页面没有标签块）。"""
    f = OUT / "catalog.json"
    if not f.exists():
        return {}
    return {e["id"]: e.get("cats") or [] for e in json.loads(f.read_text(encoding="utf-8"))["poems"]}


def main() -> int:
    cats = load_catalog()
    ids = []
    for line in (OUT / "discovered.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "id" in rec:
            ids.append(rec["id"])
    poems, missing, empty = [], 0, 0
    for order, pid in enumerate(dict.fromkeys(ids)):
        pc, mb = RAW / f"{pid}.html", RAW / f"{pid}.m.html"
        src = pc if pc.exists() and pc.stat().st_size > 800 else \
            (mb if mb.exists() and mb.stat().st_size > 800 else None)
        if src is None:
            missing += 1
            continue
        rec = parse_detail(pid, src.read_text(encoding="utf-8", errors="replace"))
        if not rec or len(rec["text"]) < 4:
            empty += 1
            continue
        rec["order"] = order
        rec["no_tags"] = src is mb
        for c in cats.get(pid, []):
            if c not in rec["tags"]:
                rec["tags"].append(c)
        yf = RAW / f"{pid}.yin.html"
        rec["py_site"] = parse_pinyin(yf.read_text(encoding="utf-8", errors="replace")) \
            if yf.exists() else []
        poems.append(rec)
    (OUT / "poems.raw.json").write_text(
        json.dumps(poems, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    stats = {
        "discovered": len(ids),
        "not_fetched": missing,
        "parse_failed": empty,
        "parsed": len(poems),
        "with_yiwen": sum(1 for p in poems if p["yiwen"]),
        "with_zhushi": sum(1 for p in poems if p["zhushi"]),
        "with_shangxi": sum(1 for p in poems if p["shangxi"]),
        "with_annotation": sum(1 for p in poems if p["yiwen"] or p["zhushi"]),
        "authors": len({p["author"] for p in poems}),
        "dynasties": len({p["dynasty"] for p in poems}),
        "tags": len({t for p in poems for t in p["tags"]}),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
