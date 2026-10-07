"""把解析结果压成 Android assets 用的紧凑 JSON。

省空间策略：
  * 作者 / 朝代 / 主题全部走字典表，诗文里只存下标
  * 平行数组而不是对象数组，省掉每首诗重复的字段名
  * 拼音只保留生僻字（不在 GB2312 一级字库的汉字），且按出现顺序只存音节
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets"

MAX_SECTION = 1400


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF


def gb_level(ch: str) -> int:
    """1=常用字(GB2312一级) 2=次常用 3=更生僻/不在库内。"""
    try:
        raw = ch.encode("gb2312")
    except UnicodeEncodeError:
        return 3
    return 1 if (raw[0] - 0xA0) <= 55 else 2


def crop(text: str) -> str:
    if len(text) <= MAX_SECTION:
        return text
    cut = text[:MAX_SECTION]
    nl = cut.rfind("\n")
    return (cut[:nl] if nl > 200 else cut) + "……"


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    poems = json.loads((OUT / "poems.raw.json").read_text(encoding="utf-8"))
    authors, dynasties, tags, rare = {}, {}, {}, []
    cols = {k: [] for k in ("id", "ti", "au", "dy", "tx", "py", "tg", "yw", "zs", "bj", "jx", "sx")}
    stats = {"annotated": 0, "poems": 0, "no_text": 0}

    def bag_id(bag: dict, key: str) -> int:
        if key not in bag:
            bag[key] = len(bag)
        return bag[key]

    for p in sorted(poems, key=lambda x: x["id"]):
        text = p["text"].strip()
        if len(text) < 2:
            stats["no_text"] += 1
            continue
        pyl = {ch: py for py, ch in p.get("py", []) if py and is_cjk(ch)}
        seq, used = [], set()
        for ch in text:
            if is_cjk(ch) and gb_level(ch) >= 2:
                read = pyl.get(ch)
                if read:
                    seq.append(read)
                    if ch not in used:
                        used.add(ch)
                        rare.append(ch)
        cols["py"].append(" ".join(seq))
        stats["annotated"] += len(seq)
        stats["poems"] += 1
        cols["id"].append(p["id"])
        cols["ti"].append(p["title"])
        cols["au"].append(bag_id(authors, p["author"] or "佚名"))
        cols["dy"].append(bag_id(dynasties, p["dynasty"] or "先秦"))
        cols["tx"].append(text)
        cols["tg"].append(
            ",".join(str(bag_id(tags, t)) for t in dict.fromkeys(p["cats"] + p["tags"]))
        )
        cols["yw"].append(crop(p["yiwen"]))
        cols["zs"].append(crop(p["zhushi"]))
        cols["bj"].append(crop(p["beijing"]))
        cols["jx"].append(crop(p["jianxi"]))
        cols["sx"].append(crop(p["shangxi"]))

    payload = {
        "v": 1,
        "n": len(cols["id"]),
        "src": "数据来源：公开语料与公开网络资料。诗词正文属公有领域，注释译文赏析版权归原作者所有，仅作个人学习研究用途",
        "authors": list(authors),
        "dynasties": list(dynasties),
        "tags": list(tags),
        "rare": "".join(rare),
        **cols,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (ASSETS / "poems.json").write_text(blob, encoding="utf-8")
    gz = len(gzip.compress(blob.encode("utf-8"), 9))
    print(
        f"poems={payload['n']} authors={len(payload['authors'])} "
        f"dynasties={len(payload['dynasties'])} tags={len(payload['tags'])} "
        f"rare={len(payload['rare'])} drop={stats['no_text']}\n"
        f"json={len(blob.encode('utf-8'))/1048576:.2f}MB gzip≈{gz/1048576:.2f}MB "
        f"avg_rare_per_poem={stats['annotated']/max(stats['poems'],1):.1f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
