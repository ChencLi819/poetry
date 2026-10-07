#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语料库门禁：每次重建 poems.db 之后校验一组不变量。

用法：
    python tools/check_db.py                       # 校验 App 资产里的库
    python tools/check_db.py --db data/_snap.db    # 校验快照 / 候选库
    python tools/check_db.py --strict              # WARN 也算失败
    python tools/check_db.py --json                # 机器可读输出（接进构建流水线）

退出码：
    0  通过（可能有 WARN，除非 --strict）
    1  有 FAIL（或 --strict 下有 WARN）—— 门禁拦住
    2  脚本自身的问题（库不存在 / 打不开），与语料质量无关

数据库只读打开（mode=ro），不写任何文件。H* 是硬失败：App 会崩或会显示错数据；
W* 是质量提示：不阻断。阈值集中在下面的常量区，调阈值不用碰逻辑。

注意 py 的下标是 UTF-16 码元下标（Ruby.java 直接拿它 index Java String），
所以本文件里所有长度/下标都按 UTF-16 码元算，不能用 Python 码点。
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from array import array
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "android" / "app" / "src" / "main" / "assets" / "poems.db"

# ------------------------------------------------------------------ 可调常量
MAX_EXAMPLES = 3            # 每条检查最多打印几个例子
EXAMPLE_CHARS = 60          # 单个例子截断长度
TX_MIN_LEN = 4              # 正文最短（UTF-16 码元，与 Java String.length() 同口径）
W_PREQIN_SHARE = 0.02       # dy='先秦' 占比阈值：绝大多数作品应属唐宋元
W_UNKNOWN_SHARE = 0.01      # dy='未知' 占比阈值
W_NOISE_TAGS = ("诗词大会", "必背", "失调名", "课外", "阅读与")   # 子串命中即算噪声标签
W_NO_REALTAG_SHARE = 0.50   # "只有合集名标签 / 完全没标签"的行占比阈值
W_TONELESS_SHARE = 0.10     # py 中无调号音节占比阈值
VALID_PROV = ("gs", "cp")
ANNOT_COLS = ("yw", "zs", "bj", "jx", "sx")
COLLECTION_TAGS = {          # 合集 / 选本名：不算"真标签"
    "全唐诗", "全宋诗", "全清诗", "全金诗", "全元诗", "全明诗",
    "宋词", "元曲", "唐诗", "宋诗", "乐府诗集", "古诗源",
}

RE_CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]")
RE_HTML = re.compile(r"</?[A-Za-z][A-Za-z0-9_.:\-]{0,20}[^>]{0,60}>")
RE_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|apos|nbsp|copy|reg|#\d+|#x[0-9a-fA-F]+);")
RE_WEB = re.compile(r"charset\s*=|https?://|window\.|javascript:|document\.", re.I)
RE_DOUBLE_SP = re.compile(r"[ \u3000]{2}")
RE_ORPHAN_NUM = re.compile(
    r"[ \u3000]+(?:其\s*[〇零一二三四五六七八九十百]{1,4}"
    r"|[〇零一二三四五六七八九十百]{1,5}"
    r"|[0-9]{1,4}"
    r"|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]{1,5})$")
RE_GAP = re.compile(r"[□〖〗\[\]]")
RE_IDX = re.compile(r"[0-9]+")
RE_PINYIN = re.compile(r"^[A-Za-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüńň]{1,12}$")

HAN_RANGES = ((0x3400, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x2FA1F), (0x30000, 0x3134F))

TONE_GROUPS = (("a", "āáǎà"), ("e", "ēéěè"), ("i", "īíǐì"),
               ("o", "ōóǒò"), ("u", "ūúǔù"), ("v", "ǖǘǚǜü"))
TONE_MARKS = set("".join(g[1] for g in TONE_GROUPS))
STRIP_TONE = {}
for _base, _chars in TONE_GROUPS:
    for _ch in _chars:
        STRIP_TONE[_ch] = _base
STRIP_TONE["ń"] = "n"
STRIP_TONE["ň"] = "n"

# 常见音节表：声母 × 韵母的笛卡尔积，是个故意宽松的超集（j/q/x/y 后的 ü 按正规写法
# 拼成 u，所以 ue/van 之类都得留着），只用来兜住明显乱写的拼音。命中不了的一律当
# "可疑"提示，不做硬失败，避免误伤真实但冷门的音节。
INITIALS = [""] + list("bpmfdtnlgkhjqxrzcsyw") + ["zh", "ch", "sh"]
FINALS = (["a", "o", "e", "i", "u", "v", "ai", "ei", "ui", "ao", "ou", "iu", "ie", "ve",
           "ue", "er", "an", "en", "in", "un", "vn", "ang", "eng", "ing", "ong", "iong",
           "ia", "ian", "iang", "iao", "ua", "uai", "uan", "uang", "ue", "uo", "v",
           "iou", "uei", "uen", "van", "ueng", "n", "ng", "m"])
VALID_SYL = {i + f for i in INITIALS for f in FINALS} | {"e", "ê", "o", "hm", "hng", "n", "ng"}


def is_han(cp):
    return any(lo <= cp <= hi for lo, hi in HAN_RANGES)


def u16(s):
    """字符串 -> UTF-16 码元数组（Java String 的口径）。"""
    return array("H", s.encode("utf-16-le"))


def norm_syl(s):
    return "".join(STRIP_TONE.get(c, c) for c in s).lower()


def blank(v):
    return v is None or not str(v).strip()


try:                        # 与构建脚本共用同一签名，才能判断"去重是否守住"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from textutil import sig as dedup_sig          # type: ignore
except Exception:           # 单文件拷走也能跑
    _PUNCT = re.compile(r"[，。、；：！？「」『』“”‘’（）《》〈〉【】\s,.;:!?'\"()\[\]{}·\-—－~～]")

    def dedup_sig(text):
        return _PUNCT.sub("", text or "")[:64]


# ------------------------------------------------------------------ 结果容器
class Bucket(object):
    """计数 + 最多保留 MAX_EXAMPLES 个例子。"""

    def __init__(self, cap=None):
        self.n = 0
        self.ex = []
        self.cap = MAX_EXAMPLES if cap is None else cap   # 运行时读，支持 --max-examples

    def hit(self, ex=""):
        self.n += 1
        if len(self.ex) < self.cap:
            self.ex.append(ex)


def merge(*buckets):
    out = Bucket()
    for b in buckets:
        out.n += b.n
        for e in b.ex:
            if len(out.ex) < out.cap:
                out.ex.append(e)
    return out


class Report(object):
    def __init__(self):
        self.rows = []

    def add(self, no, name, hard, n, ex=(), note=""):
        self.rows.append({
            "no": no,
            "name": name,
            "kind": "hard" if hard else "soft",
            "status": ("FAIL" if hard else "WARN") if n else "PASS",
            "count": int(n),
            "examples": [str(e)[:EXAMPLE_CHARS] for e in list(ex)[:MAX_EXAMPLES]],
            "note": note,
        })

    def add_b(self, no, name, hard, bucket, note=""):
        self.add(no, name, hard, bucket.n, bucket.ex, note)

    @property
    def fails(self):
        return [r for r in self.rows if r["status"] == "FAIL"]

    @property
    def warns(self):
        return [r for r in self.rows if r["status"] == "WARN"]


def ex_of(rid, what, extra=""):
    return ("%s %s %s" % (rid or "?", what, extra)).strip()


def around(s, m, width=24):
    """取命中点前后一小段，比从头截 60 字有用得多。"""
    a = max(0, m.start() - width)
    b = min(len(s), m.end() + width)
    return "%s%s%s" % ("…" if a else "", s[a:b], "…" if b < len(s) else "")


# ------------------------------------------------------------------ py 逐条校验
def check_py(rid, units, n16, spec, stats):
    """校验一行注音，返回该行的行级命中信息（命中数按行计，条数进 stats）。"""
    struct, charset, odd = [], [], []
    toneless = 0
    for item in spec.split(" "):
        if not item:
            continue
        stats["syl"] += 1
        colon = item.find(":")
        if colon <= 0:
            struct.append(ex_of(rid, "py 缺冒号", repr(item)))
            continue
        head, syl = item[:colon], item[colon + 1:]
        if not RE_IDX.match(head):
            struct.append(ex_of(rid, "下标非十进制整数", repr(item)))
            continue
        if not syl:
            struct.append(ex_of(rid, "冒号后为空", repr(item)))
            continue
        if not RE_PINYIN.match(syl):
            charset.append(ex_of(rid, "拼音非法（汉字/符号/过长）", repr(item)))
        if any(c in TONE_MARKS for c in syl) or syl[-1].isdigit():
            stats["toned"] += 1
        else:
            stats["toneless"] += 1
            toneless = 1
        base = norm_syl(syl)
        if base not in VALID_SYL:
            odd.append(ex_of(rid, "音节可疑", repr(item)))
        at = int(head)
        if at >= n16:
            struct.append(ex_of(rid, "下标越界 len(tx)=%d" % n16, repr(item)))
            continue
        cu = units[at]
        if 0xDC00 <= cu <= 0xDFFF:                    # 落在低代理上，Java 会错位
            struct.append(ex_of(rid, "下标落在低代理", repr(item)))
            continue
        if 0xD800 <= cu <= 0xDBFF:
            nxt = units[at + 1] if at + 1 < n16 else 0
            if not 0xDC00 <= nxt <= 0xDFFF:
                struct.append(ex_of(rid, "代理对不完整", repr(item)))
                continue
            cp = 0x10000 + ((cu - 0xD800) << 10) + (nxt - 0xDC00)
        else:
            cp = cu
        if not is_han(cp):
            struct.append(ex_of(rid, "该位不是汉字 U+%04X" % cp, repr(item)))
    stats["struct_items"] += len(struct)
    stats["charset_items"] += len(charset)
    stats["odd_items"] += len(odd)
    return struct, charset, toneless, odd


# ------------------------------------------------------------------ 主体
def run(con, rep):
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    need = ("poem", "tag", "facet", "meta")
    missing = [t for t in need if t not in tables]
    if missing:
        rep.add("H00", "表结构齐全（poem/tag/facet/meta）", True, len(missing),
                ["缺表: %s" % ",".join(missing)], "表不全时其余检查无法进行")
        return
    rep.add("H00", "表结构齐全（poem/tag/facet/meta/zi）", True,
            0 if "zi" in tables else 1, [] if "zi" in tables else ["zi 表缺失"],
            "现有表: %s" % ",".join(sorted(tables)))

    total = con.execute("select count(*) from poem").fetchone()[0]
    meta = dict(con.execute("select k, v from meta"))

    # ---------------- H01 行数 == meta.count
    mc = meta.get("count")
    bad = 0 if (mc is not None and str(mc) == str(total)) else 1
    rep.add("H01", "poem 行数与 meta.count 一致", True, bad,
            [] if not bad else ["poem=%d meta.count=%r" % (total, mc)],
            "行数=%d version=%r authors=%r dynasties=%r annotated=%r" % (
                total, meta.get("version"), meta.get("authors"),
                meta.get("dynasties"), meta.get("annotated")))

    # ---------------- H02 prov 取值
    b_prov = Bucket()
    prov_dist = Counter()
    for v, n in con.execute("select prov, count(*) from poem group by prov"):
        prov_dist[v] = n
        if v not in VALID_PROV:
            b_prov.n += n
            if len(b_prov.ex) < b_prov.cap:
                b_prov.ex.append("prov=%r 共 %d 行" % (v, n))

    # ---------------- H03 id 唯一且非空
    n_null = con.execute("select count(*) from poem where id is null or trim(id)=''").fetchone()[0]
    n_dist = con.execute("select count(distinct id) from poem").fetchone()[0]
    n_dup = total - n_dist
    b_id = Bucket()
    b_id.n = n_null + n_dup
    if n_null:
        b_id.ex.append("id 为空/NULL %d 行" % n_null)
    for r in con.execute("select id, count(*) c from poem group by id having c>1 limit 3"):
        b_id.ex.append("重复 id=%s 出现 %d 次" % r)

    # ---------------- 逐行扫描（一趟做完所有要看内容的检查）
    empties = {c: Bucket() for c in ("ti", "tx", "au", "dy")}
    pb = {"py_struct": Bucket(), "py_charset": Bucket(), "odd_syl": Bucket()}
    b_short = Bucket()
    b_ctrl = Bucket()
    b_html = Bucket()
    b_web = Bucket()
    b_noann = Bucket()
    b_dblsp = Bucket()
    b_orphan = Bucket()
    b_gap = Bucket()
    b_anon = Bucket()
    b_au_book = Bucket()
    b_noise = Bucket()
    b_no_realtag = Bucket()
    stats = {"syl": 0, "toned": 0, "toneless": 0, "py_rows": 0, "toneless_rows": 0,
             "struct_items": 0, "charset_items": 0, "odd_items": 0}
    dy_count = Counter()
    sig_count = {}
    sig_owner = {}
    dup_ex = []

    cur = con.execute("select id,ti,au,dy,tx,py,tg,%s,prov from poem" % ",".join(ANNOT_COLS))
    for row in cur:
        rid, ti, au, dy, tx, py, tg = row[:7]
        anns = row[7:7 + len(ANNOT_COLS)]
        prov = row[7 + len(ANNOT_COLS)]
        ti = ti or ""
        au = au or ""
        tx = tx or ""
        py = py or ""
        tg = tg or ""

        for cname, val in (("ti", ti), ("tx", tx), ("au", au), ("dy", dy)):
            if blank(val):
                empties[cname].hit(ex_of(rid, "%s 为空" % cname))

        n16 = len(tx.encode("utf-16-le")) // 2
        if n16 < TX_MIN_LEN:
            b_short.hit(ex_of(rid, "tx 过短 len=%d" % n16, repr(tx)))

        m = RE_CTRL.search(tx)
        if m:
            b_ctrl.hit(ex_of(rid, "控制字符 U+%04X" % ord(m.group(0)), repr(around(tx, m, 18))))
        debris = None
        for field, label in ((ti, "ti"), (tx, "tx")):
            m = RE_HTML.search(field) or RE_ENTITY.search(field)
            if m:
                debris = ex_of(rid, "%s 残留 %s" % (label, m.group(0)[:16]),
                               repr(around(field, m, 16)))
                break
        if debris:
            b_html.hit(debris)
        for field, label in ((ti, "ti"), (tx, "tx")):
            m = RE_WEB.search(field)
            if m:
                b_web.hit(ex_of(rid, "%s 网页碎片 %s" % (label, m.group(0)[:14]),
                               repr(around(field, m, 18))))
                break

        if prov == "gs" and all(blank(v) for v in anns):
            b_noann.hit(ex_of(rid, "gs 行 yw/zs/bj/jx/sx 全空"))

        if py:
            stats["py_rows"] += 1
            f_struct, f_charset, f_toneless, f_odd = check_py(rid, u16(tx), n16, py, stats)
            if f_struct:
                pb["py_struct"].hit(f_struct[0])
            if f_charset:
                pb["py_charset"].hit(f_charset[0])
            if f_odd:
                pb["odd_syl"].hit(f_odd[0])
            if f_toneless:
                stats["toneless_rows"] += 1

        if RE_DOUBLE_SP.search(ti):
            b_dblsp.hit(ex_of(rid, "标题含双空格", repr(ti)))
        if RE_ORPHAN_NUM.search(ti):
            b_orphan.hit(ex_of(rid, "标题以孤立序号结尾", repr(ti)))
        m = RE_GAP.search(tx)
        if m:
            b_gap.hit(ex_of(rid, "正文含 %s" % m.group(0), repr(around(tx, m, 16))))
        if au in ("佚名", "无名氏"):
            b_anon.hit(ex_of(rid, "作者=%s" % au))
        if "《" in au:
            b_au_book.hit(ex_of(rid, "作者含《", repr(au)))

        dy_count[dy or "(空)"] += 1

        tags = [t for t in tg.split(",") if t]
        noise = sorted({t for t in tags for k in W_NOISE_TAGS if k in t})
        if noise:
            b_noise.hit(ex_of(rid, "噪声标签 %s" % ",".join(noise)[:24]))
        if not [t for t in tags if t not in COLLECTION_TAGS]:
            b_no_realtag.hit(ex_of(rid, "无真标签 tg=%r" % tg[:24]))

        s = dedup_sig(tx)
        if s:
            c = sig_count.get(s)
            if c is None:
                sig_count[s] = 1
                sig_owner[s] = rid
            else:
                sig_count[s] = c + 1
                if c == 1 and len(dup_ex) < MAX_EXAMPLES:
                    dup_ex.append("%s ~ %s 签名相同" % (sig_owner[s], rid))

    # ---------------- 汇总硬失败
    rep.add_b("H02", "prov 只能是 %s" % "/".join(VALID_PROV), True, b_prov,
              "实际分布: %s" % ", ".join("%s=%d" % (k or "(NULL)", v)
                                         for k, v in prov_dist.most_common()))
    rep.add_b("H03", "id 唯一且非空", True, b_id)
    b_empty = merge(*[empties[c] for c in ("ti", "tx", "au", "dy")])
    rep.add_b("H04", "ti/tx/au/dy 非空", True, b_empty,
              "分项: %s" % " ".join("%s=%d" % (c, empties[c].n)
                                    for c in ("ti", "tx", "au", "dy")))
    rep.add_b("H05", "tx 长度 >= %d（UTF-16 码元）" % TX_MIN_LEN, True, b_short)
    rep.add_b("H06", "py 结构合法（十进制下标/非空/下标<len(tx)/该位是汉字而非低代理）",
              True, pb["py_struct"],
              "命中按行计；注音行 %d 行，非法条目 %d 条" % (stats["py_rows"], stats["struct_items"]))
    rep.add_b("H07", "py 拼音部分只允许拉丁字母+声调符号（不得是汉字）", True, pb["py_charset"],
              "命中按行计；非法条目 %d 条" % stats["charset_items"])
    rep.add_b("H10", "正文不含控制字符", True, b_ctrl)
    rep.add_b("H11", "标题/正文无 HTML 标签残留与未解码实体", True, b_html)
    rep.add_b("H12", "gs 行至少一个注释字段非空", True, b_noann,
              "meta.annotated=%r" % meta.get("annotated"))
    rep.add_b("H14", "标题/正文无网页碎片（charset= / http:// / window.）", True, b_web)

    check_tag_fk(con, rep)
    check_facet(con, rep)
    if "zi" in tables:
        check_zi(con, rep)
    else:
        rep.add("H13", "zi 单字且说明字段非空", True, 1, ["zi 表缺失"])

    # ---------------- 提示项
    rep.add_b("W01", "标题含双空格", False, b_dblsp)
    rep.add_b("W02", "标题以孤立序号结尾（「 其一」「  五四」）", False, b_orphan)
    rep.add_b("W03", "正文含 □ / 〖〗 / 半角 []", False, b_gap)
    rep.add_b("W04", "作者为佚名/无名氏", False, b_anon)
    rep.add_b("W05", "作者含《（出处串到作者位）", False, b_au_book)

    preqin = dy_count.get("先秦", 0)
    unknown = dy_count.get("未知", 0)
    dy_ex = []
    n_dy_bad = 0
    if preqin > W_PREQIN_SHARE * max(total, 1):
        n_dy_bad += preqin
        dy_ex.append("先秦 %d 行（%.2f%%）> 阈值 %.1f%%" % (
            preqin, 100.0 * preqin / max(total, 1), 100 * W_PREQIN_SHARE))
    if unknown > W_UNKNOWN_SHARE * max(total, 1):
        n_dy_bad += unknown
        dy_ex.append("未知 %d 行（%.3f%%）> 阈值 %.1f%%" % (
            unknown, 100.0 * unknown / max(total, 1), 100 * W_UNKNOWN_SHARE))
    top = dy_count.most_common(3)
    rep.add("W06", "朝代分布异常（先秦/未知 占比）", False, n_dy_bad, dy_ex,
            "dy 取值 %d 种；实际占比 先秦=%.2f%% 未知=%.3f%%；头部 %s" % (
                len(dy_count), 100.0 * preqin / max(total, 1),
                100.0 * unknown / max(total, 1),
                ", ".join("%s=%d" % (k, v) for k, v in top)))

    rep.add_b("W07", "噪声标签（黑名单：%s）" % "/".join(W_NOISE_TAGS), False, b_noise)
    rep.add("W08", "除合集名外没有真标签的行占比", False,
            b_no_realtag.n if b_no_realtag.n > W_NO_REALTAG_SHARE * max(total, 1) else 0,
            b_no_realtag.ex,
            "%d/%d 行（%.1f%%）只有合集名或无标签，阈值 %.0f%%；合集名集合 %s" % (
                b_no_realtag.n, total, 100.0 * b_no_realtag.n / max(total, 1),
                100 * W_NO_REALTAG_SHARE, ",".join(sorted(
                    COLLECTION_TAGS & {t for t, _ in
                                       con.execute("select tag, count(*) from tag "
                                                   "group by tag having count(*)>1000")}))))

    clusters = {s: c for s, c in sig_count.items() if c > 1}
    dup_rows = sum(clusters.values())
    rep.add("W09", "近似重复（去标点全篇签名聚簇）", False, dup_rows, dup_ex,
            "签名 %d 个；>=2 行的簇 %d 个，涉及 %d 行" % (len(sig_count), len(clusters), dup_rows))

    tl, wtl = stats["toneless"], stats["toned"]
    n_syl = tl + wtl
    w10_ex = []
    w10_n = 0
    if tl > W_TONELESS_SHARE * max(n_syl, 1):
        w10_n += stats["toneless_rows"]
        w10_ex.append("无调号音节 %d/%d（%.1f%%）> 阈值 %.0f%%，涉及 %d 行" % (
            tl, n_syl, 100.0 * tl / max(n_syl, 1), 100 * W_TONELESS_SHARE,
            stats["toneless_rows"]))
    if pb["odd_syl"].n:
        w10_n += pb["odd_syl"].n
        w10_ex.extend(pb["odd_syl"].ex)
    rep.add("W10", "py 注音可疑（无调号音节占比 + 不在常见音节表）", False, w10_n, w10_ex,
            "音节 %d 条 / 注音行 %d 行；无调号 %.2f%%（%d 行），非常见音节 %d 条（%d 行）" % (
                n_syl, stats["py_rows"], 100.0 * tl / max(n_syl, 1),
                stats["toneless_rows"], stats["odd_items"], pb["odd_syl"].n))


def check_tag_fk(con, rep):
    try:
        n_orphan = con.execute(
            "select count(*) from tag t left join poem p on t.pid=p.id where p.id is null"
        ).fetchone()[0]
        ex = ["孤儿 pid=%s" % r[0] for r in con.execute(
            "select distinct t.pid from tag t left join poem p on t.pid=p.id "
            "where p.id is null limit %d" % MAX_EXAMPLES)]
        n_tag = con.execute("select count(*) from tag").fetchone()[0]
    except sqlite3.Error as e:
        n_orphan, ex, n_tag = 1, ["tag 表不可查: %s" % e], -1
    rep.add("H08", "tag.pid 都能在 poem.id 找到", True, n_orphan, ex,
            "tag 行数=%d" % n_tag)


def check_facet(con, rep):
    actual = {}
    for kind, col in (("author", "au"), ("dynasty", "dy"), ("src", "src")):
        actual[kind] = {k: v for k, v in con.execute(
            "select %s, count(*) from poem group by %s" % (col, col)) if k}
    actual["tag"] = dict(con.execute("select tag, count(*) from tag group by tag"))

    declared = {}
    bad_kind = Bucket()
    n_facet = 0
    for kind, name, n in con.execute("select kind, name, n from facet"):
        n_facet += 1
        if kind not in actual:
            bad_kind.hit("facet.kind 非法: %r" % (kind,))
            continue
        declared.setdefault(kind, {})[name or ""] = n

    n_diff = bad_kind.n
    ex = list(bad_kind.ex)
    for kind in ("author", "dynasty", "tag", "src"):
        act, dec = actual[kind], declared.get(kind, {})
        miss = [k for k in act if k not in dec]
        extra = [k for k in dec if k not in act]
        wrong = [k for k in set(act) & set(dec) if act[k] != dec[k]]
        n_diff += len(miss) + len(extra) + len(wrong)
        if len(ex) < MAX_EXAMPLES and miss:
            ex.append("%s 缺条目 %r（实算 %d 行）" % (kind, miss[0], act[miss[0]]))
        if len(ex) < MAX_EXAMPLES and extra:
            ex.append("%s 多余条目 %r" % (kind, extra[0]))
        if len(ex) < MAX_EXAMPLES and wrong:
            k = wrong[0]
            ex.append("%s 计数不符 %r facet=%d 实算=%d" % (kind, k, dec[k], act[k]))
    rep.add("H09", "facet 计数与 poem/tag 实算一致（误差>0 即失败）", True, n_diff, ex,
            "facet 行数=%d；实算 author=%d dynasty=%d tag=%d" % (
                n_facet, len(actual["author"]), len(actual["dynasty"]), len(actual["tag"])))


def is_latin(ch):
    """拉丁字母与带调元音：字典里出现它们只可能是拼音，正文说明句不会以它开头。"""
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("\u00c0" <= ch <= "\u02ff")


def check_zi(con, rep):
    b_char = Bucket()
    b_allblank = Bucket()
    b_leak = Bucket()
    n_zi = 0
    for zi, senses, gloss, evidence, phrase, form in con.execute(
            "select zi, senses, gloss, evidence, phrase, form from zi"):
        n_zi += 1
        if zi is None or len(str(zi)) != 1:
            b_char.hit("zi=%r 不是单字" % (zi,))
        if all(blank(v) for v in (senses, gloss, evidence, phrase, form)):
            b_allblank.hit("zi=%r 的说明字段全空" % (zi,))
        # 字头+拼音行没被切开就会整段掉进释义/古义，如"啀ái 1.犬斗貌"、"窗chu|āng窗户"
        for name, val in (("senses", senses), ("gloss", gloss)):
            v = (val or "").lstrip()
            if not v:
                continue
            if is_latin(v[0]):
                b_leak.hit("%s.%s 以拼音碎片开头: %r" % (zi, name, v[:18]))
            elif v[0] == zi and len(v) > 1 and is_latin(v[1]):
                b_leak.hit("%s.%s 泄漏字头+拼音: %r" % (zi, name, v[:18]))
        if (form or "").lstrip()[:1] in ("(", "（"):
            b_leak.hit("%s.form 没剥掉括号: %r" % (zi, form[:18]))
    merged = merge(b_char, b_allblank)
    rep.add_b("H13", "zi 表：单字 + senses/gloss/evidence/phrase 至少一项非空", True, merged,
              "zi 行数=%d；分项 非单字=%d 说明全空=%d" % (
                  n_zi, b_char.n, b_allblank.n))
    rep.add_b("H15", "zi 释义/古义无字头与拼音残留，字形说解已剥括号", True, b_leak,
              "命中 %d 行" % b_leak.n)


# ------------------------------------------------------------------ 输出
def print_text(rep, db, secs, strict):
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    rows = sorted(rep.rows, key=lambda r: (order[r["status"]], r["no"]))
    print("check_db  %s" % db)
    print("=" * 96)
    for r in rows:
        print("[%-7s] %-4s %-52s 命中 %d" % (r["no"], r["status"], r["name"][:52], r["count"]))
        if r["note"]:
            print("            %s" % r["note"][:160])
        for e in r["examples"]:
            print("            · %s" % e)
    print("-" * 96)
    n_pass = sum(1 for r in rep.rows if r["status"] == "PASS")
    print("合计 %d 项：FAIL %d / WARN %d / PASS %d   用时 %.1fs" % (
        len(rep.rows), len(rep.fails), len(rep.warns), n_pass, secs))
    for r in rep.fails:
        print("  硬失败 %s %s（命中 %d）" % (r["no"], r["name"], r["count"]))
    for r in rep.warns:
        print("  提示   %s %s（命中 %d）" % (r["no"], r["name"], r["count"]))
    if strict and rep.warns:
        print("--strict：以上 WARN 一并视为失败")


def main(argv=None):
    global MAX_EXAMPLES
    ap = argparse.ArgumentParser(description="poems.db 不变量门禁（只读，退出码即结果）")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="要校验的 SQLite 文件")
    ap.add_argument("--strict", action="store_true", help="WARN 也当失败")
    ap.add_argument("--json", action="store_true", dest="as_json", help="机器可读输出")
    ap.add_argument("--max-examples", type=int, default=3, help="每条最多打印几个例子")
    args = ap.parse_args(argv)

    MAX_EXAMPLES = max(0, args.max_examples)

    if hasattr(sys.stdout, "reconfigure"):        # 本机控制台是 GBK
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    path = Path(args.db)
    if not path.is_file():
        sys.stderr.write("数据库不存在: %s\n" % path)
        return 2
    uri = "file:%s?mode=ro" % path.resolve().as_posix()
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as e:
        sys.stderr.write("打不开数据库: %s\n" % e)
        return 2

    rep = Report()
    t0 = time.time()
    try:
        run(con, rep)
    finally:
        con.close()
    secs = time.time() - t0

    rc = 1 if (rep.fails or (args.strict and rep.warns)) else 0
    if args.as_json:
        print(json.dumps({
            "db": str(path), "ok": rc == 0, "strict": args.strict,
            "seconds": round(secs, 1), "exit": rc,
            "summary": {"total": len(rep.rows), "fail": len(rep.fails),
                        "warn": len(rep.warns),
                        "pass": sum(1 for r in rep.rows if r["status"] == "PASS")},
            "checks": rep.rows,
        }, ensure_ascii=False, indent=1))
    else:
        print_text(rep, str(path), secs, args.strict)
    return rc


if __name__ == "__main__":
    sys.exit(main())
