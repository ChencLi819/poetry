"""生成 App 用的 SQLite 语料库。

只收有注释或译文的作品（这是"每篇都带注释"的硬门槛），并按采集顺序排序。
生僻字注音取三级来源：本篇来源拼音（按位置对齐）> 单音字本地字典 > 该字多数读法；
三者都拿不准就不标，宁缺勿错。清洗与去重签名统一走 textutil，和 build_public.py 同一口径。
"""
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pypinyin import pinyin, Style

from textutil import (ANON, COLLECTION_DYNASTY, clean_tags, normalize_body,
                      normalize_title, sig, split_author)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets"

CAPS = {"yiwen": 500, "zhushi": 900, "beijing": 400, "jianxi": 400, "shangxi": 900}
SOURCE_NOTE = "注释译文：公开网络资料，版权归原作者所有 · 正文：chinese-poetry 公开语料（MIT）"
UNKNOWN_DY = "未知"

# 朝代写法归一；拿不到朝代时不再默认先秦，宁可标未知
DY_ALIAS = {"唐": "唐代", "宋": "宋代", "元": "元代", "明": "明代", "清": "清代",
            "汉": "两汉", "西汉": "两汉", "东汉": "两汉", "秦": "先秦", "战国": "先秦",
            "春秋": "先秦", "春秋战国": "先秦", "隋": "隋代", "五代十国": "五代",
            "金": "金朝", "近代": "近现代", "当代": "近现代", "三国": "魏晋",
            "两汉": "两汉", "先秦": "先秦", "魏晋": "魏晋", "南北朝": "南北朝",
            "隋代": "隋代", "五代": "五代", "金朝": "金朝", "唐代": "唐代", "宋代": "宋代",
            "元代": "元代", "明代": "明代", "清代": "清代", "近现代": "近现代", "启蒙": "启蒙"}
# 合法音节：拉丁字母 + 带调元音，其余（把汉字本身当拼音、残留控制符）一律丢掉
SYLLABLE = re.compile(r"^[A-Za-zàáǎāēéěèīíǐìōóǒòūúǔùǖǘǚǜü]{1,12}$")
WHITESPACE = re.compile(r"\s")


def gb_level(ch: str) -> int:
    try:
        raw = ch.encode("gb2312")
    except UnicodeEncodeError:
        return 3
    return 1 if raw[0] - 0xA0 <= 55 else 2


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF


def crop(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    nl = cut.rfind("\n")
    return (cut[:nl] if nl > 120 else cut) + "……"


def unit_index(text: str, pos: int) -> int:
    """Python 码点下标 -> Java 下标。"""
    return len(text[:pos].encode("utf-16-le")) // 2


def clean_syllable(s: str) -> str:
    s = (s or "").strip()
    return s if SYLLABLE.match(s) else ""


def site_readings(p: dict) -> dict:
    """注音页按「标题+作者+〔朝代〕+正文」逐字给读法。

    旧实现把读法按字归并（own_map.setdefault(ch, py)），同一个字在标题里读过
    「长 cháng」，正文里的「长 zhàng」就被首见读法套掉了；这里改成按下标对齐。
    """
    text = p["text"]
    pairs = [(clean_syllable(py), ch) for py, ch in (p.get("py_site") or []) if ch]
    pairs = [(py, ch) for py, ch in pairs if py]
    if not pairs or not text:
        return {}
    hint = p.get("_prefix_len", 0)
    marks = [i for i, (_, c) in enumerate(pairs) if c == "〕" and i < 80]
    if marks:
        start = marks[-1] + 1
    else:
        head = "".join(ch for ch in text[:10] if not WHITESPACE.match(ch))
        start, best = hint, -1
        for s in range(max(0, hint - 8), min(len(pairs), hint + 12)):
            score = sum(1 for k, ch in enumerate(head) if s + k < len(pairs) and pairs[s + k][1] == ch)
            if score > best:
                start, best = s, score
    res, j = {}, 0
    for py, ch in pairs[start:]:
        k = text.find(ch, j)
        if k < 0:
            continue
        res[k] = py
        j = k + 1
    return res


def build_pinyin(poems):
    """先汇总来源给过的读法（只取正文段，按位置），再逐首生成注音。"""
    site_pref = {}
    votes = {}
    for p in poems:
        m = p["_site_map"]
        text = p["text"]
        for pos, py in m.items():
            votes.setdefault(text[pos], Counter())[py] += 1
    for ch, c in votes.items():
        site_pref[ch] = c.most_common(1)[0][0]

    single = {}

    def reading(ch):
        if ch not in single:
            single[ch] = [r for r in pinyin(ch, style=Style.TONE, heteronym=True)[0]
                          if clean_syllable(r)]
        return single[ch]

    stats = Counter()
    for p in poems:
        text = p["text"]
        own = p["_site_map"]
        out = []
        for i, ch in enumerate(text):
            if not is_cjk(ch) or gb_level(ch) < 2:
                continue
            r = own.get(i)
            src = "site"
            if not r:
                cand = reading(ch)
                if len(cand) == 1:
                    r, src = cand[0], "mono"
                elif ch in site_pref:
                    r, src = site_pref[ch], "site-pref"
                else:
                    continue
            if r:
                out.append(f"{unit_index(text, i)}:{r}")
                stats[src] += 1
        p["py"] = " ".join(out)
    return stats


def tidy(p: dict) -> dict:
    """入库前统一清洗：正文/标题规范化，作者拆出出处，标签去掉合集名·噪声·与标题重复的词牌。"""
    raw_title = p.get("title") or ""
    raw_author = p.get("author") or ""
    raw_dy = (p.get("dynasty") or "").strip()
    p["_prefix_len"] = len(raw_title) + len(raw_author) + (len(raw_dy) + 2 if raw_dy else 0)
    p["text"] = normalize_body(p.get("text") or "")
    p["title"] = normalize_title(raw_title) or normalize_title(p["text"].split("\n")[0][:12])
    p["_dynasty_raw"] = raw_dy
    au, au_src = split_author(raw_author)
    p["_author"] = au
    tags, coll = clean_tags(p.get("tags") or [], p["title"])
    p["_tags"] = tags
    p["_src"] = "·".join(dict.fromkeys(
        [s for s in [(p.get("src") or "").strip(), au_src] if s] + coll))
    return p


def author_dynasties(items) -> dict:
    """同作者的主朝代：只从确实抓到朝代的作品里统计。"""
    votes = defaultdict(Counter)
    for p in items:
        dy = DY_ALIAS.get(p["_dynasty_raw"], p["_dynasty_raw"])
        if dy and p["_author"] != ANON:
            votes[p["_author"]][dy] += 1
    return {au: c.most_common(1)[0][0] for au, c in votes.items()}


def resolve_dynasty(p: dict, author_dy: dict) -> str:
    """抓不到〔朝代〕时的兜底：先按合集/标签推，再按同作者主朝代推，都不成立就标未知。"""
    dy = p["_dynasty_raw"]
    dy = DY_ALIAS.get(dy, dy)
    if dy:
        return dy
    for name in p["_src"].split("·") + p["_tags"]:
        if name in COLLECTION_DYNASTY:
            return COLLECTION_DYNASTY[name]
    if p["_author"] != ANON:
        cand = author_dy.get(p["_author"])
        if cand:
            return cand
    return UNKNOWN_DY


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    poems = [tidy(p) for p in json.loads((OUT / "poems.raw.json").read_text(encoding="utf-8"))]
    for p in poems:
        p["prov"] = "gs"
    public_path = OUT / "public.raw.json"
    public = []
    if public_path.exists():
        public = [tidy(p) for p in
                  json.loads(public_path.read_text(encoding="utf-8"))]
        for p in public:
            p["prov"] = "cp"
    for p in poems + public:
        p["_site_map"] = site_readings(p)
    stats = build_pinyin(poems + public)
    author_dy = author_dynasties(poems + public)

    seen, rows = set(), []
    for p in sorted(poems, key=lambda x: x.get("order", 1 << 30)):
        if not (p["yiwen"] or p["zhushi"]):
            continue
        # 正文全是标点时签名为空，这种脏数据不参与去重、也不许被顺手丢掉（总数不能降）
        key = sig(p["text"]) or f"keep:{p['id']}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(p)
    # 公开语料只有正文，注释等精注语料备齐后按签名回填
    for p in sorted(public, key=lambda x: x.get("order", 1 << 30)):
        key = sig(p["text"])
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(p)

    for p in rows:
        p["_dynasty"] = resolve_dynasty(p, author_dy)

    db_path = ASSETS / "poems.db"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    c = con.cursor()
    c.executescript(
        """
        CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE poem(
            id TEXT PRIMARY KEY, ord INTEGER, pv TEXT,
            ti TEXT, au TEXT, dy TEXT, tx TEXT, py TEXT, tg TEXT,
            yw TEXT, zs TEXT, bj TEXT, jx TEXT, sx TEXT, src TEXT, prov TEXT);
        CREATE INDEX poem_ord ON poem(ord);
        CREATE INDEX poem_au ON poem(au);
        CREATE INDEX poem_dy ON poem(dy);
        CREATE INDEX poem_ti ON poem(ti);
        CREATE INDEX poem_prov ON poem(prov);
        CREATE TABLE tag(pid TEXT, tag TEXT);
        CREATE INDEX tag_name ON tag(tag);
        CREATE TABLE facet(kind TEXT, name TEXT, n INTEGER);
        """
    )
    facet = Counter()
    for p in rows:
        names = p["_tags"]
        c.execute(
            "INSERT INTO poem VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p["id"], p.get("order", 0), p["text"].split("\n")[0][:48],
             p["title"], p["_author"], p["_dynasty"], p["text"], p["py"],
             ",".join(names), crop(p["yiwen"], CAPS["yiwen"]), crop(p["zhushi"], CAPS["zhushi"]),
             crop(p["beijing"], CAPS["beijing"]), crop(p["jianxi"], CAPS["jianxi"]),
             crop(p["shangxi"], CAPS["shangxi"]), p["_src"], p.get("prov", "gs")),
        )
        for t in names:
            c.execute("INSERT INTO tag VALUES(?,?)", (p["id"], t))
            facet[("tag", t)] += 1
        facet[("author", p["_author"])] += 1
        facet[("dynasty", p["_dynasty"])] += 1
        if p["_src"]:
            facet[("src", p["_src"])] += 1
    for (kind, name), n in facet.items():
        c.execute("INSERT INTO facet VALUES(?,?,?)", (kind, name, n))
    meta = {
        "version": "2",
        "count": str(len(rows)),
        "source": SOURCE_NOTE,
        "authors": str(len({p["_author"] for p in rows})),
        "dynasties": str(len({p["_dynasty"] for p in rows})),
        "annotated": str(sum(1 for p in rows if p["yiwen"] or p["zhushi"])),
    }
    c.executemany("INSERT INTO meta VALUES(?,?)", meta.items())
    con.commit()
    con.close()
    version = f"{len(rows)}-{int(db_path.stat().st_mtime)}"
    (ASSETS / "db.ver").write_text(version, encoding="utf-8")
    legacy = ASSETS / "poems.json"
    if legacy.exists():
        legacy.unlink()
    size = db_path.stat().st_size
    import gzip

    gz = len(gzip.compress(db_path.read_bytes(), 9))
    dy_stat = Counter(p["_dynasty"] for p in rows)
    print(json.dumps({
        "kept": len(rows), "annotated": len(poems), "public": len(public),
        "text_only": sum(1 for p in rows if not (p["yiwen"] or p["zhushi"])),
        "pinyin_sources": dict(stats),
        "db_mb": round(size / 1048576, 1), "gzipped_mb": round(gz / 1048576, 1),
        "authors": meta["authors"], "dynasties": meta["dynasties"],
        "annotated": meta["annotated"],
        "dynasty_top": dy_stat.most_common(8),
        "dynasty_fixed_by_tag": sum(1 for p in rows
                                    if not p["_dynasty_raw"] and p["_dynasty"] != UNKNOWN_DY),
        "dynasty_unknown": dy_stat[UNKNOWN_DY],
        "with_src": sum(1 for p in rows if p["_src"]),
        "with_real_tag": sum(1 for p in rows if p["_tags"]),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
