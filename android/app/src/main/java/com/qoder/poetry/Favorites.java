package com.qoder.poetry;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** 收藏只落在本地 SharedPreferences，不依赖网络。 */
public class Favorites {

    private final SharedPreferences sp;
    private final Set<String> ids = new HashSet<>();

    public Favorites(Context ctx) {
        sp = ctx.getSharedPreferences("fav", Context.MODE_PRIVATE);
        ids.addAll(sp.getStringSet("ids", new HashSet<>()));
    }

    public synchronized boolean has(String id) {
        return ids.contains(id);
    }

    public synchronized Set<String> ids() {
        return new HashSet<>(ids);
    }

    /** @return 切换后的收藏状态 */
    public synchronized boolean toggle(String id) {
        if (ids.remove(id)) {
            save();
            return false;
        }
        ids.add(id);
        save();
        return true;
    }

    private void save() {
        sp.edit().putStringSet("ids", new HashSet<>(ids)).apply();
    }
}
