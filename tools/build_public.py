"""导入 chinese-poetry 公开语料：繁转简、按热度挑名篇、与已有注释去重。

这一步先把"量"补上（正文 + 作者 + 朝代 + 拼音），注释留待精注语料备齐后按签名回填。
清洗规则和签名都从 textutil 取，保证和 build_db.py 是同一个口径。
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from textutil import ANON, clean_tags, fold, normalize_body, normalize_title, sig, split_author

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "vendor" / "chinese-poetry-master"
DATA = ROOT / "data"

# 默认全量收录；需要瘦身时改成具体数字即可
TOP_TANG = TOP_SONG = TOP_YUAN = 1 << 30
EDITORIAL = re.compile(r"\[([^\]\[\n]{1,3})\]")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))



def rank_score(entry):
    if not isinstance(entry, dict):
        return 0
    return sum(int(entry.get(k) or 0) for k in ("baidu", "google", "bing", "bing_en", "so360"))


def load_ranked(shard_dir, rank_dir, prefix):
    """分片与排行榜分片按索引一一对应。"""
    out = []
    for f in sorted(Path(shard_dir).glob(prefix + ".*.json")):
        m = re.search(r"(\d+)\.json$", f.name)
        if not m:
            continue
        poems = load(f)
        rf = Path(rank_dir) / f"{prefix.rsplit('.', 1)[0]}.rank.{m.group(1)}.json"
        ranks = load(rf) if rf.exists() else []
        for i, p in enumerate(poems):
            if isinstance(p, dict):
                p["_score"] = rank_score(ranks[i]) if i < len(ranks) else 0
                out.append(p)
    return out


def norm(text):
    if not text:
        return ""
    # 语料里 [扁] 这类是校勘标记：保留括号里的用字，只去掉括号本身
    text = EDITORIAL.sub(r"\1", text)
    return fold(text)


def as_lines(body):
    """各集合的正文字段形态不一，统一成字符串列表。"""
    if isinstance(body, str):
        return [body]
    out = []
    if isinstance(body, list):
        for x in body:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                out.extend(as_lines(x.get("content") or x.get("text")
                                    or x.get("paragraphs") or []))
    return out


def make(idn, title, author, dynasty, lines, tags, score, src=""):
    lines = [normalize_body(norm(l)).strip() for l in as_lines(lines)]
    text = "\n".join(l for l in lines if l)
    title = normalize_title(norm(title or ""))
    if not text or len(text) < 6:
        return None
    # 语料里混进的网页响应头/导航碎片，整篇丢弃
    if any(m in text for m in ("charset=", "Content-Type", "http://", "https://",
                               "window.", "Last-Modified")):
        return None
    if not title:
        title = normalize_title(text.split("\n")[0][:12]) or "无题"
    au, au_src = split_author(norm(author or ANON))
    srcs = [s for s in (src, au_src) if s]
    real_tags, coll = clean_tags([norm(t).strip() for t in tags if t], title)
    srcs += coll
    return {"id": idn, "title": title, "author": au, "dynasty": dynasty, "text": text,
            "tags": real_tags, "src": "·".join(dict.fromkeys(srcs)), "yiwen": "", "zhushi": "",
            "beijing": "", "jianxi": "", "shangxi": "", "py_site": [], "_score": score}


def collect():
    items = []

    print("读全唐诗…", flush=True)
    for p in load_ranked(SRC / "全唐诗", SRC / "rank" / "poet", "poet.tang"):
        items.append(make(None, p.get("title"), p.get("author"), "唐代",
                          p.get("paragraphs") or [], [], p.get("_score", 0), "全唐诗"))
    for p in load_ranked(SRC / "全唐诗", SRC / "rank" / "poet", "poet.song"):
        items.append(make(None, p.get("title"), p.get("author"), "宋代",
                          p.get("paragraphs") or [], [], p.get("_score", 0), "全宋诗"))
    print("读宋词…", flush=True)
    for p in load_ranked(SRC / "宋词", SRC / "rank" / "ci", "ci.song"):
        cipai = norm(p.get("rhythmic") or "").strip()
        # 词牌写进标题就够了，再当一次标签只会和标题重复
        title = cipai + ("·" + norm(p.get("title")).strip() if p.get("title") else "")
        items.append(make(None, title, p.get("author"), "宋代",
                          p.get("paragraphs") or [], [], p.get("_score", 0), "宋词"))
    print("读元曲与经典…", flush=True)
    for p in load(SRC / "元曲" / "yuanqu.json"):
        items.append(make(None, p.get("title"), p.get("author"), "元代",
                          p.get("paragraphs") or [], [], 1, "元曲"))

    for p in load(SRC / "诗经" / "shijing.json"):
        part = "·".join(x for x in (norm(p.get("chapter") or "").strip(),
                                    norm(p.get("section") or "").strip()) if x)
        items.append(make(None, p.get("title"), "", "先秦", p.get("content") or [],
                          [part], 100, "诗经"))
    for p in load(SRC / "楚辞" / "chuci.json"):
        items.append(make(None, p.get("title"), p.get("author") or "屈原", "先秦",
                          p.get("content") or [], [], 100, "楚辞"))
    for p in load(SRC / "论语" / "lunyu.json"):
        items.append(make(None, p.get("chapter"), "", "先秦",
                          p.get("paragraphs") or [], [], 100, "论语"))

    for f in (SRC / "四书五经").glob("*.json"):
        d = load(f)
        if isinstance(d, dict) and "paragraphs" in d:
            chapter = norm(d.get("chapter"))
            items.append(make(None, d.get("chapter"), "", "先秦",
                              d.get("paragraphs") or [], [], 60, chapter or "四书五经"))
    for f in (SRC / "蒙学").glob("*.json"):
        d = load(f)
        if isinstance(d, dict):
            body = d.get("paragraphs") or d.get("content") or d.get("para") or []
            items.append(make(None, d.get("title"), d.get("author") or "",
                              "启蒙", body if isinstance(body, list) else [str(body)],
                              [], 60, norm(d.get("title") or "") or "蒙学"))
    for p in load(SRC / "纳兰性德" / "纳兰性德诗集.json"):
        items.append(make(None, p.get("title"), p.get("author"), "清代",
                          p.get("para") or [], [], 40, "纳兰性德"))
    for f in (SRC / "五代诗词").rglob("*.json"):
        d = load(f)
        if not isinstance(d, list):
            continue
        for p in d:
            if isinstance(p, dict) and p.get("paragraphs"):
                items.append(make(None, p.get("title") or p.get("rhythmic"), p.get("author"),
                                  "五代", p["paragraphs"], [], p.get("_score", 5), "五代诗词"))
    for p in load(SRC / "曹操诗集" / "caocao.json"):
        items.append(make(None, p.get("title"), "曹操", "两汉",
                          p.get("paragraphs") or [], [], 40, "曹操诗集"))
    return [i for i in items if i]


def main() -> int:
    # 只与精注语料已抓结果去重；不能读 poems.db，否则会把上一轮的公开正文误判成重复丢掉
    existing = set()
    raw = DATA / "poems.raw.json"
    if raw.exists():
        for p in json.loads(raw.read_text(encoding="utf-8")):
            if p.get("yiwen") or p.get("zhushi"):
                existing.add(sig(p["text"]))

    all_items = collect()
    dedup = {}
    for it in all_items:
        s = sig(it["text"])
        if not s or s in existing:
            continue
        prev = dedup.get(s)
        if prev is None or it["_score"] > prev["_score"]:
            dedup[s] = it
    pool = list(dedup.values())

    buckets = {"tang": [], "song": [], "yuan": [], "other": []}
    for it in pool:
        src = it["src"]
        key = ("tang" if "全唐诗" in src or "全宋诗" in src else "song" if "宋词" in src
               else "yuan" if "元曲" in src else "other")
        buckets[key].append(it)

    def top(lst, limit):
        return sorted(lst, key=lambda x: -x["_score"])[:limit]

    kept = (top(buckets["tang"], TOP_TANG) + top(buckets["song"], TOP_SONG)
            + top(buckets["yuan"], TOP_YUAN) + buckets["other"])
    kept.sort(key=lambda p: -p["_score"])
    used = set()
    for i, p in enumerate(kept):
        base = "cp" + hashlib.md5(sig(p["text"]).encode()).hexdigest()[:10]
        pid, n = base, 1
        while pid in used:            # 34 万条量级下短哈希会撞车
            n += 1
            pid = f"{base}-{n}"
        used.add(pid)
        p["id"] = pid
        p["order"] = 10_000_000 + i
    (DATA / "public.raw.json").write_text(
        json.dumps(kept, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"parsed": len(all_items), "unique": len(dedup),
                      "kept": len(kept), "skipped_dup_of_annotated": len(all_items) - len(dedup)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
