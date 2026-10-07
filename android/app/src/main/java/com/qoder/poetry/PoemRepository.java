package com.qoder.poetry;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.os.Handler;
import android.os.Looper;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** 只读 SQLite 语料库；35 万篇规模下靠分层检索与索引保证响应。 */
public class PoemRepository {

    public interface ReadyListener {
        void onReady();
    }

    public static class Facet {
        public final String name;
        public final int count;

        Facet(String n, int c) {
            name = n;
            count = c;
        }
    }

    /**
     * 分类条目上限：facet 表按篇数倒序，超出上限的只是最冷门的一长尾。
     * 作者条目实测上万，不设上限会让整张表常驻在适配器里。
     */

    private final List<ReadyListener> listeners = new ArrayList<>();
    private final Handler main = new Handler(Looper.getMainLooper());
    /** 单线程串行访问只读连接：避免并发共用一条连接，也让深 OFFSET 排队而不是互相抢 IO。 */
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private SQLiteDatabase db;

    volatile Db.Progress progress;

    private volatile Context app;
    private volatile boolean ready;
    private volatile boolean loaded;
    private volatile String error = "";
    private volatile int percent;
    private volatile int total;
    private volatile int authors;

    public void setProgress(Db.Progress p) {
        progress = p;
    }

    /** 进度既支持回调，界面也可以轮询取用；回调一律切回主线程，见下面的 sink。 */
    public int progressPercent() {
        return percent;
    }

    public boolean isReady() {
        return ready;
    }

    /** 加载线程已经结束（不论成功或失败）。 */
    public boolean isLoaded() {
        return loaded;
    }

    /** 已尝试加载但没拿到可用的库——和「还没加载完」「真的就绪」两种状态都要区分开。 */
    public boolean isFailed() {
        return loaded && !ready;
    }

    public String errorMessage() {
        return error;
    }

    /** 所有查库请求走这条队列。 */
    public void bg(Runnable r) {
        worker.execute(r);
    }

    /** 查完回主线程填 UI。 */
    public void ui(Runnable r) {
        main.post(r);
    }

    /**
     * 解压线程的进度回调：读的是「此刻」的 progress 字段，所以 Activity 在 loadAsync
     * 之后才注册也来得及；同时把 setText 切回主线程，避免后台线程直接改 View。
     */
    private final Db.Progress sink = new Db.Progress() {
        @Override
        public void onPercent(final int p) {
            percent = p;
            final Db.Progress target = progress;
            if (target == null) return;
            main.post(new Runnable() {
                @Override
                public void run() {
                    target.onPercent(p);
                }
            });
        }
    };

    public void loadAsync(final Context ctx) {
        if (ready || loaded) return;
        app = ctx.getApplicationContext();
        final Context a = app;
        worker.execute(new Runnable() {
            @Override
            public void run() {
                open(a);
            }
        });
    }

    /** 失败后的重试入口：重置状态再走一遍后台加载，l 会在新一次结束时收到回调。 */
    public void retry(Context ctx, ReadyListener l) {
        if (!loaded) return;
        if (l != null) {
            synchronized (listeners) {
                if (!listeners.contains(l)) listeners.add(l);
            }
        }
        loaded = false;
        ready = false;
        error = "";
        percent = 0;
        final Context a = ctx.getApplicationContext();
        app = a;
        worker.execute(new Runnable() {
            @Override
            public void run() {
                open(a);
            }
        });
    }

    /** 后台线程里跑，任何异常都不允许把线程弄死：否则 loaded 永远不为 true，遮罩再也撤不掉。 */
    private void open(Context a) {
        if (a == null) {
            error = "no context";
            finish();
            return;
        }
        Db helper = new Db();
        try {
            if (helper.open(a, sink)) {
                SQLiteDatabase opened = helper.get();
                db = opened;
                total = metaInt(opened, "count");
                authors = metaInt(opened, "authors");
                ready = true;
                error = "";
            } else {
                closeQuietly();
                error = helper.errorMessage();
            }
        } catch (Throwable t) {
            ready = false;
            error = t.getMessage() == null ? t.getClass().getSimpleName() : t.getMessage();
        } finally {
            finish();
        }
    }

    private void closeQuietly() {
        try {
            if (db != null) db.close();
        } catch (Exception ignored) {
        }
        db = null;
    }

    private void finish() {
        loaded = true;
        List<ReadyListener> snapshot;
        synchronized (listeners) {
            snapshot = new ArrayList<>(listeners);
            listeners.clear();
        }
        // 逐个 post：某个监听器里再注册或抛异常，都不会影响其余监听器收到通知
        for (final ReadyListener l : snapshot) {
            main.post(new Runnable() {
                @Override
                public void run() {
                    l.onReady();
                }
            });
        }
    }

    public void whenReady(ReadyListener l) {
        if (l == null) return;
        if (loaded) {
            // 已经有结论（就绪或失败），直接回放；调用方用 isReady()/isFailed() 分辨
            l.onReady();
            return;
        }
        synchronized (listeners) {
            if (!listeners.contains(l)) listeners.add(l);
        }
    }

    public void removeReadyListener(ReadyListener l) {
        if (l == null) return;
        synchronized (listeners) {
            listeners.remove(l);
        }
    }

    public int size() {
        return total;
    }

    /** meta 表里已经存了作者数，首页只要计数时不必把 facet 整张捞出来。 */
    public int authorCount() {
        return authors;
    }

    private static int metaInt(SQLiteDatabase d, String key) {
        Cursor c = null;
        try {
            c = d.rawQuery("SELECT v FROM meta WHERE k=?", new String[]{key});
            if (c.moveToFirst()) return Integer.parseInt(c.getString(0).trim());
        } catch (Exception e) {
            // meta 缺键或值不是数字，按 0 处理，不影响库可用
        } finally {
            if (c != null) c.close();
        }
        return 0;
    }

    private static Poem bind(Cursor c, boolean full) {
        Poem p = new Poem();
        p.id = c.getString(0);
        p.ord = c.getInt(1);
        p.title = c.getString(2);
        p.author = c.getString(3);
        p.dynasty = c.getString(4);
        p.preview = c.getString(5);
        p.pinyin = c.getString(6);
        String tg = c.getString(7);
        p.tags = tg.isEmpty() ? new String[0] : tg.split(",");
        // LIGHT（9 列）和 FULL（15 列）的第 8 列都是正文，先无条件读出来
        if (c.getColumnCount() > 8) p.text = c.getString(8);
        if (full && c.getColumnCount() > 14) {
            p.yiwen = c.getString(9);
            p.zhushi = c.getString(10);
            p.beijing = c.getString(11);
            p.jianxi = c.getString(12);
            p.shangxi = c.getString(13);
            p.source = c.getString(14);
        }
        return p;
    }

    private boolean usable() {
        return ready && db != null && db.isOpen();
    }

    private List<Poem> light(String sql, String[] args) {
        List<Poem> out = new ArrayList<>();
        if (!usable()) return out;
        Cursor c = db.rawQuery(sql, args);
        try {
            while (c.moveToNext()) out.add(bind(c, false));
        } finally {
            c.close();
        }
        return out;
    }

    public Poem byId(String id) {
        if (!usable() || id == null) return null;
        Cursor c = db.rawQuery("SELECT " + Poem.FULL + " FROM poem WHERE id=?", new String[]{id});
        try {
            return c.moveToFirst() ? bind(c, true) : null;
        } finally {
            c.close();
        }
    }

    /**
     * 35 万篇规模下的分层检索：
     *   1) 精注库（带注释的精校部分，行数少）允许全字段包含匹配，可以搜诗句；
     *   2) 公开语料只走篇名/作者前缀匹配，靠索引，避免全表扫正文。
     * 耗时随数据量增长，必须在后台线程调用。
     */
    public List<Poem> search(String query) {
        String q = query == null ? "" : query.trim();
        LinkedHashMap<String, Poem> out = new LinkedHashMap<>();
        if (q.isEmpty() || !usable()) return new ArrayList<>();
        String like = "%" + q + "%";
        Cursor c = db.rawQuery("SELECT " + Poem.LIGHT + " FROM poem WHERE prov='gs'"
                        + " AND (ti LIKE ? OR au LIKE ? OR dy LIKE ? OR tx LIKE ? OR tg LIKE ?)"
                        + " ORDER BY ord LIMIT 150",
                new String[]{like, like, like, like, like});
        try {
            while (c.moveToNext()) {
                Poem p = bind(c, false);
                out.put(p.id, p);
            }
        } finally {
            c.close();
        }
        // 上界补一个最大码位，BETWEEN 才能走 ti / au 索引做前缀匹配
        String hi = q + (char) 0xFFFF;
        c = db.rawQuery("SELECT " + Poem.LIGHT + " FROM poem"
                        + " WHERE ti BETWEEN ? AND ? OR au BETWEEN ? AND ?"
                        + " ORDER BY ti LIMIT 200",
                new String[]{q, hi, q, hi});
        try {
            while (c.moveToNext()) {
                Poem p = bind(c, false);
                out.put(p.id, p);
            }
        } finally {
            c.close();
        }
        return new ArrayList<>(out.values());
    }

    /** 点字查义：按单字取字典条目，未收录返回 null。参数是完整码点串，代理对不拆。 */
    public Zi zi(String zi) {
        if (!usable() || zi == null || zi.isEmpty()) return null;
        Cursor c = db.rawQuery("SELECT py, tr, radi, stroke, senses, gloss, form,"
                + " evidence, phrase FROM zi WHERE zi=?", new String[]{zi});
        try {
            if (!c.moveToFirst()) return null;
            return new Zi(zi, c.getString(0), c.getString(1), c.getString(2),
                    c.getInt(3), c.getString(4), c.getString(5), c.getString(6),
                    c.getString(7), c.getString(8));
        } finally {
            c.close();
        }
    }

    public int countFacet(String kind, String name) {
        if (!usable()) return 0;
        String sql = "author".equals(kind) ? "SELECT COUNT(*) FROM poem WHERE au=?"
                : "dynasty".equals(kind) ? "SELECT COUNT(*) FROM poem WHERE dy=?"
                : "src".equals(kind) ? "SELECT COUNT(*) FROM poem WHERE src=?"
                : "SELECT COUNT(*) FROM tag WHERE tag=?";
        Cursor c = db.rawQuery(sql, new String[]{name});
        try {
            return c.moveToFirst() ? c.getInt(0) : 0;
        } finally {
            c.close();
        }
    }

    /** 分类下单篇可能上万，必须分页，不能一次捞进内存。 */
    public List<Poem> byFacet(String kind, String name, int limit, int offset) {
        if (!usable()) return new ArrayList<>();
        String where = "author".equals(kind) ? "au=?" : "dynasty".equals(kind) ? "dy=?"
                : "src".equals(kind) ? "src=?" : "id IN (SELECT pid FROM tag WHERE tag=?)";
        Cursor c = db.rawQuery("SELECT " + Poem.LIGHT + " FROM poem WHERE " + where
                        + " ORDER BY ord LIMIT ? OFFSET ?",
                new String[]{name, String.valueOf(limit), String.valueOf(offset)});
        try {
            List<Poem> out = new ArrayList<>();
            while (c.moveToNext()) out.add(bind(c, false));
            return out;
        } finally {
            c.close();
        }
    }

    /** 分类条目；limit <= 0 表示不限。 */
    public List<Facet> facets(String kind, int limit) {
        List<Facet> out = new ArrayList<>();
        if (!usable()) return out;
        String sql = "SELECT name, n FROM facet WHERE kind=? ORDER BY n DESC, name"
                + (limit > 0 ? " LIMIT ?" : "");
        String[] args = limit > 0
                ? new String[]{kind, String.valueOf(limit)}
                : new String[]{kind};
        Cursor c = db.rawQuery(sql, args);
        try {
            while (c.moveToNext()) out.add(new Facet(c.getString(0), c.getInt(1)));
        } finally {
            c.close();
        }
        return out;
    }

    public List<Poem> favorites(Collection<String> ids) {
        List<Poem> out = new ArrayList<>();
        if (!usable()) return out;
        List<String> list = new ArrayList<>(ids);
        for (int i = 0; i < list.size(); i += 400) {
            List<String> chunk = list.subList(i, Math.min(list.size(), i + 400));
            StringBuilder ph = new StringBuilder();
            for (int j = 0; j < chunk.size(); j++) ph.append(j == 0 ? "?" : ",?");
            out.addAll(light("SELECT " + Poem.LIGHT + " FROM poem WHERE id IN (" + ph + ")"
                    + " ORDER BY ord", chunk.toArray(new String[0])));
        }
        return out;
    }

    /**
     * 任意 where 条件的分页查询，供「分类 / 主题 / 收藏」等复合筛选复用。
     * 调用方保证 where 里只带自己的 ? 占位符。
     */
    public List<Poem> query(String where, String[] args, int limit, int offset) {
        if (!usable()) return new ArrayList<>();
        String sql = "SELECT " + Poem.LIGHT + " FROM poem WHERE " + where
                + " ORDER BY ord LIMIT ? OFFSET ?";
        String[] full = new String[args.length + 2];
        System.arraycopy(args, 0, full, 0, args.length);
        full[args.length] = String.valueOf(limit);
        full[args.length + 1] = String.valueOf(offset);
        return light(sql, full);
    }

    public int count(String where, String[] args) {
        if (!usable()) return 0;
        Cursor c = db.rawQuery("SELECT COUNT(*) FROM poem WHERE " + where, args);
        try {
            return c.moveToFirst() ? c.getInt(0) : 0;
        } finally {
            c.close();
        }
    }

    /** 同一天恒定同一首，靠日期做种子而不是随机。 */
    public Poem ofTheDay(long epochDay) {
        if (!usable() || total == 0) return null;
        int offset = (int) Math.floorMod(epochDay * 2654435761L, total);
        Cursor c = db.rawQuery("SELECT " + Poem.FULL + " FROM poem ORDER BY ord LIMIT 1 OFFSET ?",
                new String[]{String.valueOf(offset)});
        try {
            return c.moveToFirst() ? bind(c, true) : null;
        } finally {
            c.close();
        }
    }

    public List<Poem> dailyPick(int count, long seed) {
        List<Poem> out = new ArrayList<>();
        if (!usable() || total == 0) return out;
        java.util.Random rnd = new java.util.Random(seed);
        java.util.Set<Integer> used = new java.util.HashSet<>();
        for (int i = 0; i < count; i++) {
            int offset = rnd.nextInt(total);
            if (!used.add(offset)) continue;
            Cursor c = db.rawQuery("SELECT " + Poem.LIGHT + " FROM poem ORDER BY ord"
                    + " LIMIT 1 OFFSET ?", new String[]{String.valueOf(offset)});
            try {
                if (c.moveToFirst()) out.add(bind(c, false));
            } finally {
                c.close();
            }
        }
        return out;
    }
}