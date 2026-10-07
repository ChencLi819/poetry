"""按页号推进的批量采集框架：目录发现与逐篇整理交替进行，多入口分摊请求。

用法：
    python tools/crawl_all.py run --pages 3200      # 交替翻目录页 + 整理详情
    python tools/crawl_all.py authors --limit 200   # 按作者翻作品列表
    python tools/crawl_all.py upgrade               # 把移动端快照补成桌面端
    python tools/crawl_all.py status

每个入口各自限速、遇限逐级退避；全部落盘、可中断续跑，
随时能用已完成的部分建库。

数据源地址由 SOURCE_BASE / MOBILE_BASE 环境变量给出（默认留空），
仓库里不预设任何具体站点；请只对你**有权访问**的资料使用本脚本。
"""
import argparse
import json
import os
import random
import re
import sys
import threading
import time
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("RAW_DIR") or (ROOT / "raw"))
DATA = ROOT / "data"
DISCOVERED = DATA / "discovered.jsonl"

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
# 退避档位：连续遇限时逐级拉长等待，避免无谓空转
COOLDOWNS = (20, 40, 75, 120, 180)
# 长时间运行时定期重开一个连接会话，避免单会话状态累积
ROTATE_EVERY = 170
_lock = threading.Lock()


class Host:
    def __init__(self, base, ua):
        self.base, self.ua = base, ua
        self.interval = 1.0
        self.next = 0.0
        self.until = 0.0        # 冷却截止时间
        self.hits = 0           # 连续触发速率限制次数
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.served = 0

    def rotate(self):
        """丢掉当前连接状态，换一个新会话；调用方需持有 _lock。"""
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.served = 0

    def wait_slot(self):
        while True:
            with _lock:
                now = time.time()
                if now < self.until:
                    wait = min(self.until - now, 5.0)
                elif now >= self.next:
                    self.next = max(now, self.next) + self.interval
                    return
                else:
                    wait = min(self.next - now, 2.0)
            time.sleep(wait)

    def busy(self):
        with _lock:
            return time.time() < self.until

    def punish(self):
        with _lock:
            self.hits += 1
            self.rotate()          # 先按"连接会话需重置"处理
            if self.hits <= 4:
                cool = 4 * self.hits
            else:
                cool = COOLDOWNS[min(self.hits - 4, len(COOLDOWNS) - 1)]
            self.until = time.time() + cool
            self.interval = min(2.5, self.interval * 1.15)
            return cool

    def reward(self):
        with _lock:
            self.hits = 0
            self.until = 0.0
            self.served += 1
            if self.served >= ROTATE_EVERY:
                self.rotate()      # 长连接主动轮换，避免单会话状态累积
            self.interval = max(0.9, self.interval * 0.9)


PC = Host((os.environ.get("SOURCE_BASE") or "https://example.invalid").rstrip("/"), UA_PC)
MOBILE = Host((os.environ.get("MOBILE_BASE") or "https://example.invalid").rstrip("/"), UA_M)
STATS = {"pc": 0, "mobile": 0, "fail": 0, "page": 0, "throttle": 0}


def fetch(host: Host, path: str, referer: str = None, tries=2):
    last = None
    for _ in range(tries):
        host.wait_slot()
        headers = {"User-Agent": host.ua, "Accept-Language": "zh-CN,zh;q=0.9",
                   "Accept": "text/html,application/xhtml+xml"}
        if referer:
            headers["Referer"] = host.base + referer
        try:
            with host.opener.open(
                    urllib.request.Request(host.base + path, headers=headers),
                    timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            host.reward()
            return body
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (512, 429, 403):
                cool = host.punish()
                with _lock:
                    STATS["throttle"] += 1
                print(f"  [{host.base}] 触发速率限制，冷却 {cool:.0f}s", flush=True)
            else:
                time.sleep(2)
        except Exception as exc:
            last = exc
            time.sleep(2)
    raise RuntimeError(f"{host.base}{path} -> {last}")


def pick(prefer_mobile=False, only=None):
    """选一个没在冷却的域名；only 用于把某个进程锁死在单一域名上。"""
    if only is not None:
        return only if not only.busy() else None
    order = (MOBILE, PC) if prefer_mobile else (PC, MOBILE)
    for h in order:
        if not h.busy():
            return h
    return None


def write_atomic(path: Path, text: str):
    tmp = Path(str(path) + ".part")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load():
    ids, pages = [], 0
    if DISCOVERED.exists():
        for line in DISCOVERED.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("page"):
                pages = max(pages, rec["page"])
            else:
                ids.append(rec["id"])
    return ids, pages


def have(pid):
    return ((RAW / f"{pid}.html").exists() and (RAW / f"{pid}.html").stat().st_size > 800) \
        or ((RAW / f"{pid}.m.html").exists()
            and (RAW / f"{pid}.m.html").stat().st_size > 800)


def saved(pid, host):
    return RAW / (f"{pid}.html" if host is PC else f"{pid}.m.html")


def fetch_detail(pid, only=None):
    if (RAW / f"{pid}.html").exists():
        return "cached"
    h = pick(only=only)
    if h is None:
        time.sleep(5)
        h = pick(only=only) or (only or PC)
    path = f"/shiwenv_{pid}.aspx"
    try:
        html = fetch(h, path, referer="/shiwens/")
    except Exception as exc:
        if only is None and h is PC:
            try:
                h, html = MOBILE, fetch(MOBILE, path, referer="/shiwens/")
            except Exception:
                with _lock:
                    STATS["fail"] += 1
                return "fail"
        else:
            with _lock:
                STATS["fail"] += 1
            return "fail"
    if "未找到对应诗文" in html or "contson" not in html:
        write_atomic(saved(pid, PC), "")
        return "dead"
    write_atomic(saved(pid, h), html)
    with _lock:
        STATS["mobile" if h is MOBILE else "pc"] += 1
    return "ok"


def discover_one(page):
    q = urllib.parse.urlencode({"page": page, "tstr": "", "astr": "", "cstr": "", "xstr": ""})
    html = fetch(PC, f"/shiwens/default.aspx?{q}", referer="/shiwens/")
    return re.findall(r"/shiwenv_([a-z0-9]{12})\.aspx", html)


def on_disk():
    """一轮一次 listdir 代替几万次 exists+stat：队列到几万条时，逐条 stat 会把
    吞吐从 1req/s 拖到 0.3，看起来像对方在限速，其实是本地 IO。
    0 字节的死链标记也算"已处理"，否则死链会永远占住队首。"""
    return set(os.listdir(RAW))


def pending(ids, disk, shard=0, parts=1):
    """两个进程都从队首取活，实测会把同一篇抓两遍（桌面+移动各一份），
    吞吐白折一半；按 id 哈希分片让它们各管各的段。"""
    return [q for q in dict.fromkeys(ids)
            if q + ".html" not in disk and q + ".m.html" not in disk
            and (int(q[:7], 16) % parts) == shard]


def run(pages, per_round, host="any", skip_discover=False, shard=0, parts=1):
    """host=desktop 只做发现；host=mobile 只做详情；any 保持原来的混合策略。"""
    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    ids, done = load()
    known = set(ids)
    rounds = 0
    start = time.time()
    print(f"起点：已发现 {len(known)}，列表页 {done}，目标 {pages} 页", flush=True)
    only = {"mobile": MOBILE, "desktop": PC}.get(host)
    disk = on_disk()
    while done < pages or True:
        # 桌面端在冷却时不要碰列表页，否则一次重试能把整个循环卡住十几分钟
        if (not skip_discover and host != "mobile"
                and done < pages and not PC.busy()):
            done += 1
            try:
                found = discover_one(done)
            except Exception as exc:
                done -= 1
                print(f"page {done + 1} 失败：{exc}", flush=True)
            else:
                new = [p for p in found if p not in known]
                known.update(new)
                with DISCOVERED.open("a", encoding="utf-8") as fh:
                    for pid in new:
                        fh.write(json.dumps({"id": pid}) + "\n")
                    fh.write(json.dumps({"page": done}) + "\n")
                with _lock:
                    STATS["page"] += 1
        ids, _ = load()
        todo = pending(ids, disk, shard, parts)
        for pid in todo[:per_round]:
            fetch_detail(pid, only=only)
        disk = on_disk()
        rounds += 1
        if rounds % 20 == 0:
            uniq = len(set(ids))
            got = uniq - len(pending(ids, disk))   # 全局计数，别把另一片的待抓算成已完成
            rate = STATS["pc"] + STATS["mobile"] + STATS["page"]
            print(f"页 {done}/{pages} 发现 {uniq} 详情 {got} 待抓 {uniq - got} "
                  f"({STATS}) {rate / max(time.time() - start, 1):.2f}req/s", flush=True)
        if not todo and (skip_discover or host == "mobile" or done >= pages):
            print("队列已排空，退出", flush=True)
            break
    print("run 结束", STATS, flush=True)


def upgrade():
    """把只有移动端快照的记录补抓成桌面端（为了拿回主题标签）。"""
    ids, _ = load()
    todo = [p for p in ids if (RAW / f"{p}.m.html").exists()
            and not (RAW / f"{p}.html").exists()]
    print(f"待补桌面端 {len(todo)} 篇", flush=True)
    for i, pid in enumerate(todo, 1):
        fetch_detail(pid, only=PC)   # 锁桌面端：退到移动端只会白抓一份没标签的
        if i % 100 == 0:
            print(f"{i}/{len(todo)} {STATS}", flush=True)
    print("upgrade 结束", STATS, flush=True)


def collection_links():
    """从已缓存的目录页里挖出全部合集入口。"""
    found = set()
    for f in list(RAW.glob("cat_*.html")) + list(RAW.glob("*.html"))[:40]:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for sec, slug in re.findall(r'href="/(gushi|wenyan)/([a-z]+)\.aspx\"', t):
            found.add((sec, slug))
    return sorted(found)


def harvest():
    """合集目录页每页能出上百个 id，比推荐流（10 个/页）高效得多。"""
    DATA.mkdir(parents=True, exist_ok=True)
    ids, _ = load()
    known = set(ids)
    links = collection_links()
    print(f"合集入口 {len(links)} 个，已有 id {len(known)}", flush=True)
    added = 0
    for sec, slug in links:
        path = f"/{sec}/{slug}.aspx"
        cache = RAW / f"cat2_{sec}_{slug}.html"
        try:
            html = cache.read_text(encoding="utf-8") if cache.exists() else fetch(PC, path, referer="/shiwens/")
        except Exception as exc:
            print(f"  {path} 失败 {exc}", flush=True)
            continue
        cache.write_text(html, encoding="utf-8")
        new = [i for i in dict.fromkeys(re.findall(r"/shiwenv_([a-z0-9]{12})\.aspx", html))
               if i not in known]
        known.update(new)
        added += len(new)
        with DISCOVERED.open("a", encoding="utf-8") as fh:
            for pid in new:
                fh.write(json.dumps({"id": pid}) + chr(10))
        print(f"  {path:28s} +{len(new):4d} 累计 {len(known)}", flush=True)
    print(f"harvest 完成，新增 {added}", flush=True)


def author_names(limit):
    """从已采到的带注释记录里取作者。资料本来收录这些作品，所以每位都值得翻一遍；
    名家（篇数多的）我们已基本收全，新 id 主要出自中小作者，因此 limit=0 时按篇数升序。"""
    import collections
    rows = json.loads((DATA / "poems.raw.json").read_text(encoding="utf-8"))
    c = collections.Counter()
    for r in rows:
        if any(r.get(k) for k in ("yiwen", "zhushi", "jianxi", "shangxi", "beijing")):
            name = (r.get("author") or "").strip()
            if name and name not in ("佚名", "无名氏"):
                c[name] += 1
    if limit:
        return [n for n, _ in c.most_common(limit)]
    return [n for n, _ in sorted(c.items(), key=lambda kv: kv[1])]


def discover_authors(limit, max_pages):
    """按作者翻作品列表：/shiwens/default.aspx?astr=名字&page=N，一页 10 条，
    翻到没有新 id 为止。主列表页（astr 为空）已经枯竭，这条流还有几十万。"""
    ids, _ = load()
    known = set(ids)
    names = author_names(limit)
    added = authors = 0
    for i, name in enumerate(names, 1):
        pages = 0
        while pages < max_pages:
            pages += 1
            q = urllib.parse.urlencode(
                {"page": pages, "tstr": "", "astr": name, "cstr": "", "xstr": ""})
            try:
                html = fetch(PC, f"/shiwens/default.aspx?{q}", referer="/shiwens/")
            except Exception as exc:
                print(f"  {name} p{pages} 失败：{exc}", flush=True)
                break
            found = [p for p in dict.fromkeys(
                re.findall(r"/shiwenv_([a-z0-9]{12})\.aspx", html)) if p not in known]
            if not found:
                break
            known.update(found)
            added += len(found)
            with DISCOVERED.open("a", encoding="utf-8") as fh:
                for pid in found:
                    fh.write(json.dumps({"id": pid, "via": name}, ensure_ascii=False)
                             + chr(10))
        authors += 1
        if authors % 10 == 0:
            print(f"作者 {authors}/{len(names)} 新增 id {added}（{STATS}）", flush=True)
    print(f"authors 结束：{authors} 位作者，新增 {added} 个 id", flush=True)


def status():
    ids, pages = load()
    ids = list(dict.fromkeys(ids))   # 文件里会有重复行，统计前先去掉
    pc = sum(1 for p in ids if (RAW / f"{p}.html").exists()
             and (RAW / f"{p}.html").stat().st_size > 800)
    mo = sum(1 for p in ids if (RAW / f"{p}.m.html").exists()
             and (RAW / f"{p}.m.html").stat().st_size > 800)
    print(json.dumps({"discovered": len(ids), "listing_pages": pages,
                      "desktop": pc, "mobile_only": max(mo - 0, 0),
                      "missing": len(ids) - len({p for p in ids if have(p)})},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--pages", type=int, default=3200)
    r.add_argument("--per-round", type=int, default=9)
    r.add_argument("--host", choices=("any", "mobile", "desktop"), default="any")
    r.add_argument("--shard", type=int, default=0, help="本进程只处理 id 哈希 % parts == shard 的那一段")
    r.add_argument("--parts", type=int, default=1)
    r.add_argument("--skip-discover", action="store_true", help="只排详情队列，不再翻列表页")
    sub.add_parser("harvest")
    au = sub.add_parser("authors")
    au.add_argument("--limit", type=int, default=200, help="按篇数取前 N 位作者")
    au.add_argument("--max-pages", type=int, default=40, help="每位作者最多翻几页")
    sub.add_parser("upgrade")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.pages, a.per_round, a.host, a.skip_discover, a.shard, a.parts)
    elif a.cmd == "harvest":
        harvest()
    elif a.cmd == "authors":
        discover_authors(a.limit, a.max_pages)
    elif a.cmd == "upgrade":
        upgrade()
    else:
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
