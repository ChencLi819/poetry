package com.qoder.poetry;

import android.content.Context;
import android.database.sqlite.SQLiteDatabase;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

/** 语料以只读 SQLite 随包发布，首次启动（或版本变化后）从 assets 释放到私有目录。 */
public class Db {

    private static final String NAME = "poems.db";
    private static final String VER = "db.ver";

    public interface Progress {
        void onPercent(int percent);
    }

    private SQLiteDatabase db;
    private String error = "";

    /** 失败原因要能直接给用户看，所以这里只放可读文案，异常细节留在日志里。 */
    public String errorMessage() {
        return error;
    }

    /** 约定：返回 false 时 errorMessage() 一定有值；本方法不向外抛异常。 */
    public boolean open(Context ctx, Progress sink) {
        error = "";
        String want;
        try {
            want = readAssetString(ctx, VER);
        } catch (Exception e) {
            want = null;
        }
        if (want == null || want.isEmpty()) {
            error = ctx.getString(R.string.db_no_version);
            return false;
        }
        File f = ctx.getDatabasePath(NAME);
        String have = ctx.getSharedPreferences("db", Context.MODE_PRIVATE)
                .getString("version", "");
        if (!want.equals(have) || !f.exists() || f.length() == 0) {
            if (!extract(ctx, f, want, sink)) return false;
        }
        try {
            db = SQLiteDatabase.openDatabase(f.getAbsolutePath(), null,
                    SQLiteDatabase.OPEN_READONLY);
            return true;
        } catch (Exception e) {
            // 文件被截断 / 版本串里的字节数不对 / 数据库损坏，都在这里兜住
            error = ctx.getString(R.string.db_broken);
            return false;
        }
    }

    private static String readAssetString(Context ctx, String name) {
        try {
            InputStream in = ctx.getAssets().open(name);
            byte[] buf = new byte[in.available()];
            int n = in.read(buf);
            in.close();
            return new String(buf, 0, Math.max(n, 0), "UTF-8").trim();
        } catch (Exception e) {
            return null;
        }
    }

    private boolean extract(Context ctx, File f, String version, Progress sink) {
        File tmp = new File(f.getParentFile(), NAME + ".tmp");
        try {
            InputStream in = ctx.getAssets().open(NAME);
            OutputStream out = new FileOutputStream(tmp);
            byte[] buf = new byte[1 << 16];
            long total = totalBytes(version);
            long done = 0;
            int n, last = -1;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                done += n;
                if (total > 0 && sink != null) {
                    int pct = (int) (done * 100 / total);
                    if (pct != last && pct % 2 == 0) {
                        last = pct;
                        sink.onPercent(pct);
                    }
                }
            }
            out.flush();
            out.close();
            in.close();
            // 释放出来的字节数和版本串里记的大小不一致，说明 assets 与版本串没成对更新
            if (total > 0 && tmp.length() != total) {
                tmp.delete();
                error = ctx.getString(R.string.db_size_mismatch);
                return false;
            }
            if (f.exists() && !f.delete()) {
                error = ctx.getString(R.string.db_extract_failed);
                return false;
            }
            if (!tmp.renameTo(f)) {
                tmp.delete();
                error = ctx.getString(R.string.db_extract_failed);
                return false;
            }
            ctx.getSharedPreferences("db", Context.MODE_PRIVATE).edit()
                    .putString("version", version).apply();
            return true;
        } catch (Exception e) {
            // 空间不足、读取中断等：清掉半成品，下次启动重来，绝不留一个截断的库
            tmp.delete();
            error = ctx.getString(R.string.db_extract_failed);
            return false;
        }
    }

    /** assets 里的库是压缩存放的，只能从版本串里拿到解压后的字节数。 */
    private static long totalBytes(String version) {
        int bar = version.indexOf('|');
        if (bar < 0) return 0;
        try {
            return Long.parseLong(version.substring(bar + 1).trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    public SQLiteDatabase get() {
        return db;
    }
}
