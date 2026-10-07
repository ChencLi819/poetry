"""把落盘的原始 HTML 解析成结构化诗文记录。"""
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from textutil import normalize_body, normalize_title  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "data"

TAG_BR = re.compile(r"<br\s*/?>", re.I)
TAG_P_BLOCK = re.compile(r"</p\s*>", re.I)
TAG_ANY = re.compile(r"<[^>]*>")
SPACE = re.compile(r"[ \t\u3000]+")
NEWLINES = re.compile(r"\n{2,}")
SCRIPT = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
NAME = re.compile(r"<h2>.*?<span[^>]*>([^<]+)</span>", re.S)


def to_text(fragment: str) -> str:
    """把 HTML 片段转成保留换行的纯文本。"""
    s = SCRIPT.sub("", fragment)
    s = re.sub(r"<img[^>]*>", "", s)
    s = TAG_BR.sub("\n", s)
    s = TAG_P_BLOCK.sub("\n", s)
    s = re.sub(r"<(div|p|h1|h2|h3)[^>]*>", "\n", s)
    s = TAG_ANY.sub("", s)
    s = html.unescape(s)
    s = s.replace("\u00a0", " ").replace("\xa0", " ")
    s = "\n".join(line.strip() for line in SPACE.sub(" ", s).split("\n"))
    s = NEWLINES.sub("\n", s)
    return s.strip("\n").strip()


H2 = re.compile(r"<h2>.*?</h2>", re.S)


def find_blocks(h: str) -> dict:
    """提取所有 contyishang 解析块，同名保留最长的一份。"""
    parts = h.split('<div class="contyishang"')
    best = {}
    for part in parts[1:]:
        part = part.split(">", 1)[1]
        name = NAME.search(part)
        if not name:
            continue
        part = H2.sub("", part)
        part = re.split(r'<div style="text-align:center', part)[0]
        text = to_text(part)
        if text.endswith("展开阅读全文"):
            text = text[: -len("展开阅读全文")].strip()
        key = name.group(1).strip()
        if len(text) > len(best.get(key, "")):
            best[key] = text
    return best


def split_sub(text: str) -> tuple:
    """从「译文 / 注释」混排块里拆出两段。"""
    lines = text.split("\n")
    out, cur = {}, []
    head = None
    for line in lines:
        if line in ("译文", "注释", "赏析", "简析"):
            if head:
                out[head] = "\n".join(cur).strip()
            head, cur = line, []
        else:
            cur.append(line)
    if head:
        out[head] = out.get(head, "") + "\n" + "\n".join(cur)
    return out.get("译文", "").strip(), out.get("注释", "").strip()


def parse_detail(pid: str, h: str) -> dict:
    # 桌面端正文块以 .tool 收尾，移动端以 .sons 收尾
    m = re.search(r'<div id="zhengwen%s">(.*?)(?:<div class="tool"|<div class="sons")' % pid,
                  h, re.S)
    if not m:
        return None
    main = m.group(1)
    t = re.search(r"<h1[^>]*>(.*?)</h1>", main, re.S)
    title = normalize_title(to_text(t.group(1))) if t else ""
    # 移动端作者行写成 <p class="source" style="...">，漏掉属性就会让作者和朝代整段丢失
    source = re.search(r'<p class="source"[^>]*>(.*?)</p>', main, re.S)
    author, dynasty = "", ""
    if source:
        txt = to_text(source.group(1))
        d = re.search(r"〔(.+?)〕", txt)
        if d:
            dynasty = d.group(1).strip()
            author = txt[: d.start()].strip()
        else:
            author = txt
        author = normalize_body(author.split("\n")[0] if "\n" in author else author)
    c = re.search(
        r'<div class="contson" id="contson%s"[^>]*>(.*?)</div>' % pid, main, re.S
    )
    body = normalize_body(to_text(c.group(1))) if c else ""
    tags = []
    tg = re.search(r'<div class="tag">(.*?)</div>', h, re.S)
    if tg:
        for q in re.findall(r"tstr=([^&\"']+)", tg.group(1)):
            tags.append(urllib.parse.unquote(q))
    blocks = find_blocks(h)
    yi, zh = split_sub(blocks.get("译文及注释", ""))
    if not zh:
        zh = blocks.get("注释", "")
    if not yi:
        yi = blocks.get("译文", "")
    if not title and body:
        title = normalize_title(body.split("\n")[0][:12])
    return {
        "id": pid,
        "title": title,
        "author": author,
        "dynasty": dynasty,
        "text": body,
        "tags": [normalize_body(t).strip() for t in tags if t],
        "yiwen": normalize_body(yi),
        "zhushi": normalize_body(zh),
        "beijing": normalize_body(blocks.get("创作背景", "")),
        "jianxi": normalize_body(blocks.get("简析", "")),
        "shangxi": normalize_body(blocks.get("赏析", "")),
    }


def parse_pinyin(h: str) -> list:
    pairs = re.findall(
        r'<span class="pinyin">([^<]*)</span><span class="hanzi"[^>]*>([^<])</span>',
        h,
    )
    return [(py.strip(), ch) for py, ch in pairs]


def main() -> int:
    catalog = json.loads((OUT / "catalog.json").read_text(encoding="utf-8"))
    poems, broken = [], []
    for entry in catalog["poems"]:
        pid = entry["id"]
        df, pf = RAW / f"{pid}.html", RAW / f"{pid}.yin.html"
        if not df.exists() or df.stat().st_size < 500:
            broken.append(pid)
            continue
        rec = parse_detail(pid, df.read_text(encoding="utf-8", errors="replace"))
        if not rec or len(rec["text"]) < 4:
            broken.append(pid)
            continue
        if pf.exists():
            rec["py"] = parse_pinyin(pf.read_text(encoding="utf-8", errors="replace"))
        rec["cats"] = entry["cats"]
        poems.append(rec)
    (OUT / "poems.raw.json").write_text(
        json.dumps(poems, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    stats = {
        "parsed": len(poems),
        "broken": len(broken),
        "with_pinyin": sum(1 for p in poems if p.get("py")),
        "with_yiwen": sum(1 for p in poems if p["yiwen"]),
        "with_zhushi": sum(1 for p in poems if p["zhushi"]),
        "with_shangxi": sum(1 for p in poems if p["shangxi"]),
        "dynasties": len({p["dynasty"] for p in poems}),
        "authors": len({p["author"] for p in poems}),
        "tags": len({t for p in poems for t in p["tags"]}),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    if broken:
        (OUT / "broken.json").write_text(json.dumps(broken), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
