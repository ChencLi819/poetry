"""跨脚本共用的文本清洗与去重签名。

parse.py / build_public.py / build_db.py 三条来源不同的语料都必须走这里同一套
清洗函数和同一个 sig()，否则两边的重复判断口径不一致，会互相漏判同一篇作品。

  fold()             繁体/异体 → 简体（复用 OpenCC 自带字表）
  sig()              去重签名：折叠繁简 + 去标点 + 取全篇前 200 字
  normalize_body()   正文清洗：统一括号、去控制符、合并空白（保留 □ 缺字符号）
  normalize_title()  标题清洗：正文规则 + 剥校勘夹注 + 合并空格 + 序号规范
  split_author()     拆作者：书名/作品名从作者位挪到出处，佚名口径归一
"""
import re
import unicodedata

# 签名截全篇前 200 字：旧版只截 64 字，长诗后半不同也会被判成同一篇，近重复漏检
SIG_LEN = 200

_PUNCT_CHARS = ("，。、；：！？､︓︔︕︖（）()《》〈〉「」『』【】〔〕〖〗“”‘’\"'"
                "·・,.;:!?'`[]{}-—–－~～_|｜‖…‥﹑＼/")
PUNCT = re.compile("[" + re.escape(_PUNCT_CHARS) + r"\s]")

# ---------------------------------------------------------------- 繁简/异体折叠
_trans = None
_phrase_re = None
_phrase_map = None
_t2s_tried = False


def _load_t2s():
    """逐条调用 OpenCC 太慢（32 万首要几十分钟），直接用它自带的字/词表批量映射。"""
    global _trans, _phrase_re, _phrase_map, _t2s_tried
    _t2s_tried = True
    try:
        import opencc
        from pathlib import Path
        d = Path(opencc.__file__).parent / "dictionary"
        pairs = {}
        for name in ("TSCharacters.txt", "TWVariants.txt"):
            for line in (d / name).read_text(encoding="utf-8").splitlines():
                f = line.split("	")
                if len(f) >= 2 and len(f[0]) == 1:
                    tgt = f[1].split(" ")[0]
                    if len(tgt) == 1:
                        pairs[f[0]] = tgt
        phrases = {}
        for line in (d / "TSPhrases.txt").read_text(encoding="utf-8").splitlines():
            f = line.split("	")
            if len(f) >= 2 and len(f[0]) > 1:
                phrases[f[0]] = f[1].split(" ")[0]
        # 长词优先，避免子串被提前替换
        _phrase_re = re.compile("|".join(re.escape(k) for k in
                                         sorted(phrases, key=len, reverse=True)))
        _phrase_map = phrases
        _trans = str.maketrans(pairs)
    except Exception:          # 没装 opencc 也不能让管线断掉，退化成不折叠
        _phrase_re = None
        _phrase_map = None
        _trans = None


def fold(text: str) -> str:
    """繁体/异体折成简体，只用于比较，不改变展示文本。"""
    if not text:
        return ""
    if not _t2s_tried:
        _load_t2s()
    if _phrase_re is None:
        return text
    return _phrase_re.sub(lambda m: _phrase_map[m.group(0)], text).translate(_trans)


def sig(text: str) -> str:
    """两版是否同一篇的判据：折叠繁简异体、去标点后取前 SIG_LEN 字。"""
    s = PUNCT.sub("", text or "")[:SIG_LEN + 40]
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = fold(s)
    return PUNCT.sub("", s)[:SIG_LEN]


# ---------------------------------------------------------------- 清洗
CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\ufffe\uffff]")
# 语料里 [扁] 这类是校勘补字：保留用字、去掉括号（丢掉用字就是丢信息）
EDITORIAL = re.compile(r"\[([^\[\]\n]{1,3})\]")
# 〖〗是古籍里的缺字/补字框，正文里统一折成全角括号；半角括号也一起统一
BRACKETS = str.maketrans({"〖": "（", "〗": "）", "[": "（", "]": "）",
                          "(": "（", ")": "）"})
WS_RUN = re.compile(r"[ \t\u00a0\u3000]{2,}")
SINGLE_WS = re.compile(r"[ \t\u00a0\u3000]+")
# 标题结尾的孤立序号：「 其一」「  五四」「 12」「 Ⅲ」
ORPHAN_SEQ = re.compile(r"\s+((?:其\s*)?[〇零一二三四五六七八九十百千]{1,5}"
                        r"|[0-9]{1,4}|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴⅵ]{1,6})\s*$")
# 标题里的校勘/编辑夹注：「（…一作…）」「（题拟）」「（节选）」「（下缺）」……
TITLE_GLOSS = re.compile(r"（[^（）]{0,300}）")
GLOSS_KEY = re.compile(r"一作|又作|原作|本作|字作|题拟|题从|题作|原缺|下缺|缺|残|误|疑|注|校|补|"
                       r"辑|附|并序|幷序|节选|选|同前|佚|据|录|《|》|[0-9０-９〇]"
                       r"|^[一二三四五六七八九十]{1,3}首$")


def _is_gloss(inner: str) -> bool:
    """括号里像不像编辑注：把内部空格去掉再判关键词。"""
    return bool(GLOSS_KEY.search(SINGLE_WS.sub("", inner)))


def normalize_body(text: str) -> str:
    """正文清洗。除控制符和空白外都是 1:1 替换，字符下标稳定，注音位置才不会错位。"""
    if not text:
        return ""
    t = CTRL.sub("", text)
    t = EDITORIAL.sub(r"\1", t)
    t = t.translate(BRACKETS)
    lines = [SINGLE_WS.sub(" ", ln).strip() for ln in t.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def normalize_title(text: str) -> str:
    """标题清洗：夹注剥掉（正文里的夹注保留）、多余空格合并、结尾序号统一成「·其一」。"""
    t = normalize_body(text)
    if not t:
        return ""
    kept = TITLE_GLOSS.sub(lambda m: "" if _is_gloss(m.group(0)[1:-1]) else m.group(0), t)
    kept = WS_RUN.sub(" ", kept).strip()
    # 超长编辑注里常常还套着「（）」，正则啃不动，按"头 + 整段尾注"的形式再切一刀
    if len(kept) > 40:
        i = kept.find("（")
        if i >= 1 and kept.endswith("）"):
            head = kept[:i].strip()
            if head:
                kept = head
    if kept:
        t = kept
    t = ORPHAN_SEQ.sub(lambda m: "·" + SINGLE_WS.sub("", m.group(1)), t)
    t = WS_RUN.sub(" ", t).strip(" ·")
    return t or normalize_body(text).strip(" ·")


# ---------------------------------------------------------------- 作者/出处
ANON = "佚名"
ANON_ALIAS = {"佚名", "无名氏", "无名", "", "-", "—", "？", "?", "（佚名）", "(佚名)"}
# 这些是书名/选本名，被语料填在作者位，应归到出处而不是作者
BOOK_AUTHORS = {"诗经", "楚辞", "论语", "孟子", "庄子", "左传", "礼记", "战国策", "史记", "汉书",
                "后汉书", "山海经", "乐府", "古诗源", "淮南子", "墨子", "韩非子", "列子",
                "世说新语", "文心雕龙", "古文观止", "尚书", "周易", "易经", "毛诗", "花间集",
                "全唐诗", "全宋诗", "宋词", "元曲", "唐诗三百首", "宋词三百首", "古诗十九首"}
# 「（唐）白居易」这种把朝代写在作者位前面的写法，朝代前缀剥掉
DY_PREFIX = re.compile(r"^（(?:唐|宋|元|明|清|汉|两汉|三国|魏晋|南北朝|五代|十国|先秦|隋|金|"
                       r"近现代|近代|当代|战国|春秋|秦|西楚|东晋|南朝|北朝)）")
# 合集名不是标签，归到出处维度；能直接确定朝代的顺便用于朝代推断
COLLECTIONS = {"全唐诗", "全宋诗", "御定全唐诗", "宋词", "元曲", "诗经", "楚辞", "论语", "四书五经",
               "蒙学", "纳兰性德", "曹操诗集", "五代诗词", "幽梦影", "水墨唐诗", "唐诗三百首",
               "宋词三百首", "古诗三百首", "宋词精选", "乐府", "古诗十九首", "婉约词", "豪放词",
               "初中古诗文", "小学古诗文", "高中古诗文", "古文观止", "小学必背", "乐府诗集",
               "楚辞精选", "汉魏六朝诗", "唐诗", "宋诗", "全清诗", "全金诗", "全明诗", "全元诗"}
COLLECTION_DYNASTY = {"全唐诗": "唐代", "御定全唐诗": "唐代", "唐诗三百首": "唐代", "全宋诗": "宋代",
                      "宋词": "宋代", "宋词精选": "宋代", "宋词三百首": "宋代", "婉约词": "宋代",
                      "豪放词": "宋代", "元曲": "元代", "诗经": "先秦", "楚辞": "先秦", "楚辞精选": "先秦",
                      "论语": "先秦", "四书五经": "先秦", "古诗十九首": "两汉", "乐府诗集": "两汉",
                      "汉魏六朝诗": "两汉", "五代诗词": "五代", "纳兰性德": "清代"}
# 节目名/教辅书单名这类标签对检索没用，纯噪声
NOISE_TAG = re.compile(r"诗词大会|必背|失调名|课外|阅读与|赏析|译文|课文|^[0-9一二三四五六七八九十]+$")


def split_author(author: str):
    """把塞在作者位的书名、作品名拆到出处，匿名统一成一个口径。返回 (作者, 出处)。"""
    a = normalize_body(author or "").strip()
    a = DY_PREFIX.sub("", a).strip()          # 「（唐）白居易」这种朝代前缀不算作者
    srcs = []
    titles = re.findall(r"《([^《》]{1,30})》", a)
    if titles:
        head = re.sub(r"《[^《》]{1,30}》", "", a).strip(" ·、,")
        srcs.extend(titles)
        a = head
    if a in ANON_ALIAS or not a:
        return ANON, "·".join(srcs)
    head = a.split("·")[0].strip()
    if head in BOOK_AUTHORS or head in COLLECTIONS:
        # 「诗经·小雅·关雎」这类整串都是书名+篇次，作者位只能是佚名
        srcs.insert(0, a)
        return ANON, "·".join(srcs)
    return a, "·".join(srcs)


def clean_tags(tags, title: str = ""):
    """标签清洗：合集名交回出处维度、噪声标签丢掉、和标题重复的词牌不再进标签。"""
    out, srcs = [], []
    t = title or ""
    for x in tags or []:
        tag = SINGLE_WS.sub("", str(x or "")).strip(" ，,、")
        if not tag or NOISE_TAG.search(tag):
            continue
        if tag in COLLECTIONS:
            if tag not in srcs:
                srcs.append(tag)
            continue
        if len(tag) >= 2 and tag in t:        # 词牌/曲牌已经写进标题了，不再当标签重复一遍
            continue
        if tag not in out:
            out.append(tag)
    return out, srcs
