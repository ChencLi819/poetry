package com.qoder.poetry;

import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/**
 * Web 前端与原生语料库之间的桥。
 *
 * 前端只发一次 {@code Android.request(envelope)}，本类在仓库的后台线程里查库，
 * 再把结果以 Base64(UTF-8 JSON) 回灌给 {@code __bridgeRecv(cb, payload)}。
 * 走 Base64 是为了彻底绕开引号、换行、U+2028 这些在 JS 字符串字面量里会咬人的字符。
 */
public class Bridge {

    /** 宿主能力：诵读、吐司、路由回传。由 Activity 实现，避免 Bridge 反向依赖具体界面。 */
    public interface Host {
        void speak(String text);

        void toast(String msg);

        void onRoute(int depth, String tab);
    }

    private static final int PAGE = 20;
    private static final int FAV_CAP = 300;

    /** 首页四个分类入口：展示字 + 对应的诗集名。 */
    private static final String[][] HOME_CATS = {
            {"唐诗", "全唐诗"}, {"宋词", "宋词"}, {"诗经", "诗经"}, {"古文", "古文观止"}
    };

    /** 热榜候选：先按「篇名+作者」精确取，取不到再退回模糊匹配。 */
    private static final String[][] RANK = {
            {"水调歌头·明月几时有", "苏轼"}, {"静夜思", "李白"}, {"将进酒", "李白"},
            {"关雎", "佚名"}, {"声声慢·寻寻觅觅", "李清照"}, {"春望", "杜甫"},
            {"登鹳雀楼", "王之涣"}, {"相思", "王维"}
    };

    private final WebView web;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final PoemRepository repo;
    private final Favorites fav;
    private final Stats stats;
    private final Host host;

    public Bridge(WebView web, PoemRepository repo, Favorites fav, Stats stats, Host host) {
        this.web = web;
        this.repo = repo;
        this.fav = fav;
        this.stats = stats;
        this.host = host;
    }

    @JavascriptInterface
    public void request(final String envelope) {
        int cb;
        String m;
        JSONObject p;
        try {
            JSONObject e = new JSONObject(envelope);
            cb = e.getInt("cb");
            m = e.getString("m");
            p = e.optJSONObject("p");
        } catch (Exception ex) {
            return;
        }
        if (p == null) p = new JSONObject();
        final int callback = cb;
        final String method = m;
        final JSONObject args = p;
        repo.bg(new Runnable() {
            @Override
            public void run() {
                Object data;
                try {
                    data = dispatch(method, args);
                } catch (Throwable t) {
                    reply(callback, err(t));
                    return;
                }
                reply(callback, ok(data));
            }
        });
    }

    /* ------------------------------------------------------------ 小接口 */

    @JavascriptInterface
    public void markRead(String id) {
        stats.markRead(id);
    }

    @JavascriptInterface
    public void markZi(String c) {
        stats.markZi(c);
    }

    @JavascriptInterface
    public void onRoute(int depth, String tab) {
        if (host != null) host.onRoute(depth, tab);
    }

    @JavascriptInterface
    public void toast(String msg) {
        if (host != null) host.toast(msg);
    }

    /* -------------------------------------------------------------- 分发 */

    private Object dispatch(String m, JSONObject p) throws Exception {
        switch (m) {
            case "boot":
                return boot();
            case "home":
                return home();
            case "picks":
                return arr(repo.dailyPick(4, p.optLong("seed", 1)));
            case "facets":
                return facets();
            case "browse":
                return browse(p.optString("dy"), p.optString("src"),
                        p.optString("tag"), p.optInt("offset"));
            case "poem":
                return poem(p.optString("id"));
            case "search":
                return search(p.optString("q"), p.optInt("offset"), p.optInt("limit"));
            case "hot":
                return hot();
            case "zi":
                return zi(p.optString("c"));
            case "ziRecent":
                return new JSONArray(stats.recentZi());
            case "favToggle":
                return fav.toggle(p.optString("id")) ? 1 : 0;
            case "favList":
                return favList(p.optInt("offset"), p.optInt("limit"));
            case "stats":
                return statsJson();
            case "speak":
                return speak(p.optString("id"));
            default:
                throw new IllegalStateException("unknown method: " + m);
        }
    }

    private JSONObject boot() throws Exception {
        JSONObject o = new JSONObject();
        o.put("count", repo.size());
        o.put("authors", repo.authorCount());
        return o;
    }

    private JSONObject home() throws Exception {
        long day = Calendar.getInstance().getTimeInMillis() / 86400000L;
        JSONObject o = new JSONObject();
        o.put("daily", poemJson(repo.ofTheDay(day), true));
        o.put("picks", arr(repo.dailyPick(4, day)));
        JSONArray cats = new JSONArray();
        for (String[] c : HOME_CATS) {
            JSONObject j = new JSONObject();
            j.put("zi", c[0]);
            j.put("name", c[1]);
            j.put("n", repo.countFacet("src", c[1]));
            cats.put(j);
        }
        o.put("cats", cats);
        return o;
    }

    private JSONObject facets() throws Exception {
        JSONObject o = new JSONObject();
        o.put("dynasties", facetArr("dynasty", 0));
        o.put("collections", facetArr("src", 12));
        o.put("tags", facetArr("tag", 20));
        return o;
    }

    private JSONArray facetArr(String kind, int limit) throws Exception {
        List<PoemRepository.Facet> list = repo.facets(kind, limit);
        JSONArray a = new JSONArray();
        for (PoemRepository.Facet f : list) {
            JSONObject j = new JSONObject();
            j.put("name", f.name);
            j.put("n", f.count);
            a.put(j);
        }
        return a;
    }

    /** 朝代 / 诗集 / 主题三者可叠加，条件为空表示不限。 */
    private JSONObject browse(String dy, String src, String tag, int offset) throws Exception {
        List<String> args = new ArrayList<>();
        StringBuilder w = new StringBuilder("1=1");
        if (!dy.isEmpty()) {
            w.append(" AND dy=?");
            args.add(dy);
        }
        if (!src.isEmpty()) {
            w.append(" AND src=?");
            args.add(src);
        }
        if (!tag.isEmpty()) {
            w.append(" AND id IN (SELECT pid FROM tag WHERE tag=?)");
            args.add(tag);
        }
        String[] a = args.toArray(new String[0]);
        JSONObject o = new JSONObject();
        o.put("total", repo.count(w.toString(), a));
        o.put("offset", offset);
        o.put("items", arr(repo.query(w.toString(), a, PAGE, offset)));
        return o;
    }

    private JSONObject poem(String id) throws Exception {
        return poemJson(repo.byId(id), true);
    }

    /**
     * 检索分页。repo.search() 每翻一页都重跑一遍 LIKE 太贵，所以把命中结果按查询词
     * 缓存住（后台单线程访问，无需加锁），之后的翻页只做切片。
     */
    private String searchQ = "";
    private List<Poem> searchHit = new ArrayList<>();

    private JSONObject search(String q, int offset, int limit) throws Exception {
        if (q == null || q.trim().isEmpty()) {
            searchQ = "";
            searchHit = new ArrayList<>();
            return page(searchHit, 0, PAGE);
        }
        if (!q.equals(searchQ)) {
            searchHit = repo.search(q);
            searchQ = q;
        }
        return page(searchHit, offset, limit <= 0 ? PAGE : limit);
    }

    /** 统一的 {total, offset, items} 切片，四个列表共用。 */
    private JSONObject page(List<Poem> all, int offset, int limit) throws Exception {
        int total = all == null ? 0 : all.size();
        JSONArray a = new JSONArray();
        int end = Math.min(total, offset + limit);
        for (int i = Math.max(0, offset); i < end; i++) a.put(poemJson(all.get(i), false));
        JSONObject o = new JSONObject();
        o.put("total", total);
        o.put("offset", offset);
        o.put("items", a);
        return o;
    }

    private JSONObject hot() throws Exception {
        JSONObject o = new JSONObject();
        JSONArray words = new JSONArray();
        List<PoemRepository.Facet> tags = repo.facets("tag", 10);
        for (PoemRepository.Facet f : tags) words.put(f.name);
        o.put("words", words);
        o.put("rank", rank());
        return o;
    }

    private JSONArray rank() throws Exception {
        JSONArray a = new JSONArray();
        for (String[] r : RANK) {
            List<Poem> hit = repo.query("ti=? AND au=?", new String[]{r[0], r[1]}, 1, 0);
            if (hit.isEmpty()) hit = repo.query("ti=?", new String[]{r[0]}, 1, 0);
            if (hit.isEmpty()) hit = repo.query("ti LIKE ?", new String[]{"%" + r[0] + "%"}, 1, 0);
            if (!hit.isEmpty()) a.put(poemJson(hit.get(0), false));
        }
        return a;
    }

    private JSONObject zi(String c) throws Exception {
        stats.markZi(c);
        Zi z = repo.zi(c);
        if (z == null) return null;
        JSONObject o = new JSONObject();
        o.put("zi", z.zi);
        o.put("py", z.pinyin);
        o.put("tr", z.traditional);
        o.put("radi", z.radical);
        o.put("stroke", z.strokes);
        o.put("senses", z.senses);
        o.put("gloss", z.gloss);
        o.put("form", z.form);
        o.put("evidence", z.evidence);
        o.put("phrase", z.phrase);
        return o;
    }

    /** 收藏夹分页。SharedPreferences 存的是无序 Set，先按 ord 排稳再做切片，否则翻页会跳。 */
    private JSONObject favList(int offset, int limit) throws Exception {
        List<Poem> all = repo.favorites(fav.ids());
        Collections.sort(all, new Comparator<Poem>() {
            @Override
            public int compare(Poem x, Poem y) {
                return x.ord < y.ord ? -1 : x.ord > y.ord ? 1 : 0;
            }
        });
        if (all.size() > FAV_CAP) all = all.subList(0, FAV_CAP);
        return page(all, offset, limit <= 0 ? PAGE : limit);
    }

    private JSONObject statsJson() throws Exception {
        JSONObject o = new JSONObject();
        o.put("read", stats.readCount());
        o.put("fav", fav.ids().size());
        o.put("zi", stats.ziCount());
        int[] week = stats.week();
        JSONArray w = new JSONArray();
        for (int v : week) w.put(v);
        o.put("week", w);
        o.put("streak", stats.streak());
        return o;
    }

    private JSONObject speak(String id) throws Exception {
        Poem p = repo.byId(id);
        JSONObject o = new JSONObject();
        if (p == null) {
            o.put("ok", false);
            o.put("msg", "这篇没有找到");
            return o;
        }
        final String text = p.title + "。" + p.text.replace("\n", "。");
        main.post(new Runnable() {
            @Override
            public void run() {
                host.speak(text);
            }
        });
        o.put("ok", true);
        return o;
    }

    /* ------------------------------------------------------------ 序列化 */

    private JSONArray arr(List<Poem> list) throws Exception {
        JSONArray a = new JSONArray();
        for (Poem p : list) a.put(poemJson(p, false));
        return a;
    }

    private JSONObject poemJson(Poem p, boolean full) throws Exception {
        JSONObject o = new JSONObject();
        if (p == null) return o;
        o.put("id", p.id);
        o.put("ti", p.title);
        o.put("au", p.author);
        o.put("dy", p.dynasty);
        o.put("pv", p.preview);
        o.put("py", p.pinyin);
        o.put("tg", new JSONArray(Arrays.asList(p.tags)));
        o.put("fav", fav.has(p.id));
        if (full) {
            o.put("tx", p.text);
            o.put("yw", p.yiwen);
            o.put("zs", p.zhushi);
            o.put("bj", p.beijing);
            o.put("jx", p.jianxi);
            o.put("sx", p.shangxi);
            o.put("src", p.source);
        }
        return o;
    }

    private static String ok(Object data) {
        try {
            JSONObject e = new JSONObject();
            e.put("data", data == null ? JSONObject.NULL : data);
            return e.toString();
        } catch (Exception ex) {
            return err(ex);
        }
    }

    private static String err(Throwable t) {
        try {
            JSONObject e = new JSONObject();
            String m = t.getMessage();
            e.put("error", m == null || m.isEmpty() ? t.getClass().getSimpleName() : m);
            return e.toString();
        } catch (Exception ex) {
            return "{\"error\":\"serialize failed\"}";
        }
    }

    private void reply(final int cb, final String json) {
        final String b64 = Base64.encodeToString(json.getBytes(StandardCharsets.UTF_8),
                Base64.NO_WRAP);
        main.post(new Runnable() {
            @Override
            public void run() {
                // b64 只含 A-Za-z0-9+/=，直接拼进字符串字面量是安全的
                web.evaluateJavascript("__bridgeRecv(" + cb + ",\"" + b64 + "\")", null);
            }
        });
    }
}
