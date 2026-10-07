"""把中华新华字典（chinese-xinhua word.json）清洗后并入 poems.db 的 zi 表。

原始 explanation 是一大段混排文本，这里按"字头+拼音"行切成古典说解与现代义项两段：
  senses   现代义项（①②③…，以及"啀ái 1.犬斗貌。"这类行内序号）
  gloss    古义说解（"同本义"、"假借为泌"…）
  form     字形说解（形声/会意…，多引《说文》）
  evidence 书证（"──《诗·周颂》"这类引文）
  phrase   词例（【毖祀】…）
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "vendor" / "chinese-xinhua-master" / "data" / "word.json"
DB = ROOT / "android" / "app" / "src" / "main" / "assets" / "poems.db"

MAX_SENSES = 8
MAX_EVIDENCE = 4
MAX_FORM = 260
BLANK = re.compile(r"\n\s*\n+")
# 拼音字母：带调元音要整段覆盖，漏了 ā(ā) 会把 "chuāng" 拆成 "chu|āng"
PIN = "a-z\u00c0-\u02ff"
# ①..⑩ 与 ⒈..⒑：现代义项的圈号序号
MARKS = "".join(chr(0x2460 + i) for i in range(10)) + \
        "".join(chr(0x2488 + i) for i in range(10)) + "【"
# 稀疏词条只用 ASCII 序号，而且整行塞了好几项："啀ái 1.犬斗貌。 2.吸饮。"
NUM = re.compile(r"(?<![\d.])\d+\s*[\.、．]\s*")


def clean_lines(text: str):
    out = []
    for raw in BLANK.sub("\n", text or "").split("\n"):
        s = raw.strip().strip("\u3000 ")
        if s:
            out.append(s)
    return out


def merge_wrapped(lines):
    """原文会在句子中间空行断开（"…于是古人就" / "采用上述四个形体…"），
    括号没配平就续到下一段，否则字形说解会剩半句、后半句掉进古义里。"""
    out, buf, depth = [], [], 0
    for s in lines:
        buf.append(s)
        depth += s.count("(") + s.count("（") - s.count(")") - s.count("）")
        if depth <= 0:
            out.append("".join(buf))
            buf, depth = [], 0
    if buf:
        out.append("".join(buf))
    return out


def split_senses(rest: str):
    """把行内的"1.犬斗貌。 2.吸饮。"拆成一行一项，序号原样保留。"""
    return clean_lines(NUM.sub(lambda m: "\n" + m.group(0).strip() + " ", rest))


def take_paren(s: str):
    """切出括号里的字形说解；括号外那句"表示惊叹或赞颂…"属于古义，不跟着进 form。"""
    depth = 0
    for i, ch in enumerate(s):
        if ch in "(（":
            depth += 1
        elif ch in ")）":
            depth -= 1
            if depth == 0:
                return s[1:i].strip(), s[i + 1:].strip(" ，,")
    return "", s


def split_entry(word: str, rec: dict):
    # 字头行可能写成"毖 bì"、贴着写"萸yú"、带异体"关（阷、関）guān"，
    # 也可能后面直接跟着现代义项"啀ái 1.犬斗貌。"——那种整行都是今义，不是古典说解
    head = re.compile(rf"^{re.escape(word)}(（[^）]*）)?\s*[{PIN}]+(?:\s+[{PIN}]+)*")
    classic, modern, seen_modern = [], [], False   # modern 元素为 (行, 是否自带字头)
    for s in clean_lines(rec.get("explanation", "")):
        if re.fullmatch(rf"[{PIN}\s]+", s):
            continue        # 字头被拆到上一段后单独剩下一行拼音，如"兹--龟兹”…" / "zi"
        m = head.match(s)
        if m:
            modern += [(x, True) for x in split_senses(s[m.end():].strip(" ，,"))]
            continue
        if s[0] in MARKS:
            seen_modern = True
        if seen_modern:
            modern.append((s, False))
        else:
            classic.append(s)

    form, kept = "", []
    for s in merge_wrapped(classic):
        if not form and s[:1] in "(（" and any(
                k in s for k in ("形声", "会意", "象形", "指事")):
            inner, tail = take_paren(s)
            if inner:
                form = inner
                if tail:
                    kept.append(tail)
                continue
        kept.append(s)
    classic = kept

    is_ev = [("--" in s or "——" in s) for s in classic]
    evidence = [re.sub(r"\s*[-—]{2,}\s*", "——", s)
                for s, flag in zip(classic, is_ev) if flag][:MAX_EVIDENCE]
    drop = {s for s, flag in zip(classic, is_ev) if flag} | {word}
    gloss = [s for s in classic if s not in drop][:6]

    # 【词例】之后的 ①② 属于词条而非本字，截断避免混进义项
    stop = next((i for i, (s, _) in enumerate(modern) if s.startswith("【")), len(modern))
    senses = [s for s, _ in modern[:stop] if len(s) > 2]   # 丢掉只有编号没有内容的行
    # 词例之后重新带字头的行（"窗cōng 1.烟突"）是本字的其他读音，仍算义项
    senses += [s for s, owned in modern[stop:] if owned and len(s) > 2]
    phrases = [s for s, _ in modern if s.startswith("【")][:6]
    return (form[:MAX_FORM], "\n".join(senses[:MAX_SENSES])[:600], "；".join(gloss)[:300],
            "\n".join(evidence)[:400], "　".join(phrases)[:220])


DUMP = ROOT / "data" / "zi.raw.json"   # 成品表备份，vendor/ 源数据集被清理后靠它重建


def build_from_vendor(c):
    n = skipped = 0
    for rec in json.loads(SRC.read_text(encoding="utf-8")):
        w = (rec.get("word") or "").strip()
        if len(w) != 1:
            skipped += 1
            continue
        form, senses, gloss, evidence, phrases = split_entry(w, rec)
        if not (senses or gloss or evidence or form or phrases):
            skipped += 1
            continue
        try:
            stroke = int(rec.get("strokes") or 0)
        except (TypeError, ValueError):
            stroke = 0
        c.execute("INSERT OR REPLACE INTO zi VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (w, (rec.get("pinyin") or "").strip(), (rec.get("oldword") or "").strip(),
                   (rec.get("radicals") or "").strip(), stroke, senses, gloss,
                   form, evidence, phrases))
        n += 1
    return n, skipped


def restore_from_dump(c):
    """没有源数据集时回填上次导出的 zi 表，字典功能不至于跟着 vendor 一起没了。"""
    d = json.loads(DUMP.read_text(encoding="utf-8"))
    cols = d["cols"]
    sql = "INSERT OR REPLACE INTO zi(%s) VALUES(%s)" % (
        ",".join(cols), ",".join("?" * len(cols)))
    for row in d["rows"]:
        c.execute(sql, [row.get(k) for k in cols])
    return len(d["rows"]), 0


def main() -> int:
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.executescript("DROP TABLE IF EXISTS zi;"
                    "CREATE TABLE zi(zi TEXT PRIMARY KEY, py TEXT, tr TEXT,"
                    " radi TEXT, stroke INTEGER, senses TEXT, gloss TEXT,"
                    " form TEXT, evidence TEXT, phrase TEXT);")
    if SRC.exists():
        n, skipped = build_from_vendor(c)
        src = "vendor"
    elif DUMP.exists():
        n, skipped = restore_from_dump(c)
        src = DUMP.name
    else:
        raise SystemExit("字典源与备份都不在：既无 %s 也无 %s" % (SRC, DUMP))
    con.commit()
    con.close()
    # 字典表并入后要刷新版本号，设备端才会重新释放数据库
    (DB.parent / "db.ver").write_text(
        f"{n}-{int(DB.stat().st_mtime)}|{DB.stat().st_size}", encoding="utf-8")
    print(json.dumps({"zi_rows": n, "skipped": skipped, "from": src,
                      "db_mb": round(DB.stat().st_size / 1048576, 1)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
