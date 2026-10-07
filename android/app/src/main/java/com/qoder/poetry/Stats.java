package com.qoder.poetry;

import android.content.Context;
import android.content.SharedPreferences;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * 「我的」页要的诵读数据：已读篇目、查过的字、按天计的诵读次数。
 *
 * 全部落在本地 SharedPreferences。按天计数只保留最近 30 天，
 * 避免偏好文件随着使用时长无限膨胀。
 */
public class Stats {

    private static final String SP = "stats";
    private static final String KEY_READ = "read";
    private static final String KEY_ZI = "zi";
    private static final String KEY_RECENT_ZI = "zi_recent";
    private static final int RECENT_ZI_MAX = 18;
    private static final int DAY_KEEP = 30;

    private final SharedPreferences sp;

    public Stats(Context ctx) {
        sp = ctx.getApplicationContext().getSharedPreferences(SP, Context.MODE_PRIVATE);
    }

    /** 打开一篇就算读过；同一篇反复打开只记一次，但每天的诵读次数照常累加。 */
    public synchronized void markRead(String id) {
        if (id == null || id.isEmpty()) return;
        Set<String> s = new HashSet<>(sp.getStringSet(KEY_READ, new HashSet<>()));
        if (s.add(id)) sp.edit().putStringSet(KEY_READ, s).apply();
        bumpToday();
        prune();
    }

    public synchronized void markZi(String c) {
        if (c == null || c.isEmpty()) return;
        Set<String> s = new HashSet<>(sp.getStringSet(KEY_ZI, new HashSet<>()));
        s.add(c);
        String recent = sp.getString(KEY_RECENT_ZI, "").replace(c, "");
        recent = (c + recent);
        if (recent.length() > RECENT_ZI_MAX) recent = recent.substring(0, RECENT_ZI_MAX);
        sp.edit().putStringSet(KEY_ZI, s).putString(KEY_RECENT_ZI, recent).apply();
    }

    public int readCount() {
        return sp.getStringSet(KEY_READ, new HashSet<>()).size();
    }

    public int ziCount() {
        return sp.getStringSet(KEY_ZI, new HashSet<>()).size();
    }

    /** 最近查过的字，新的在前。 */
    public List<String> recentZi() {
        String r = sp.getString(KEY_RECENT_ZI, "");
        List<String> out = new ArrayList<>();
        for (int i = 0; i < r.length(); i++) out.add(r.substring(i, i + 1));
        return out;
    }

    /** 最近七天（含今天）的诵读次数，按下标 0=周日 … 6=周六 对齐 Calendar。 */
    public int[] week() {
        int[] out = new int[7];
        Calendar cal = Calendar.getInstance();
        for (int back = 0; back < 7; back++) {
            Calendar d = (Calendar) cal.clone();
            d.add(Calendar.DAY_OF_YEAR, -back);
            out[d.get(Calendar.DAY_OF_WEEK) - 1] = dayCount(d);
        }
        return out;
    }

    /**
     * 连续打卡天数：今天还没读就从昨天往前算，否则今天中断一次就把连击清零太苛刻。
     * 上限 3650 天，防止极端数据下空转。
     */
    public int streak() {
        Calendar cal = Calendar.getInstance();
        if (dayCount(cal) == 0) cal.add(Calendar.DAY_OF_YEAR, -1);
        int n = 0;
        while (n < 3650 && dayCount(cal) > 0) {
            n++;
            cal.add(Calendar.DAY_OF_YEAR, -1);
        }
        return n;
    }

    private void bumpToday() {
        String k = key(Calendar.getInstance());
        sp.edit().putInt(k, sp.getInt(k, 0) + 1).apply();
    }

    private int dayCount(Calendar d) {
        return sp.getInt(key(d), 0);
    }

    private static String key(Calendar d) {
        return new SimpleDateFormat("d_yyyyMMdd", Locale.US).format(d.getTime());
    }

    /** 只留最近 30 天的按天计数，更早的键直接丢掉。 */
    private void prune() {
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.DAY_OF_YEAR, -DAY_KEEP);
        SharedPreferences.Editor ed = sp.edit();
        boolean dirty = false;
        for (String k : new HashSet<>(sp.getAll().keySet())) {
            if (!k.startsWith("d_")) continue;
            if (k.compareTo(key(cal)) < 0) {
                ed.remove(k);
                dirty = true;
            }
        }
        if (dirty) ed.apply();
    }
}
