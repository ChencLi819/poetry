package com.qoder.poetry;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.TextView;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import java.util.ArrayList;
import java.util.List;

/** 某个朝代 / 作者 / 主题下的篇目列表，边滚边取。 */
public class ListActivity extends AppCompatActivity implements PoemRepository.ReadyListener {

    public static final int MODE_DYNASTY = 0;
    public static final int MODE_AUTHOR = 1;
    public static final int MODE_TAG = 2;
    public static final int MODE_SRC = 3;

    private static final int PAGE = 200;
    private static final String KEY_MODE = "mode";
    private static final String KEY_NAME = "name";
    private static final String KEY_TAKEN = "taken";
    private static final String KEY_SCROLL = "scroll";

    private final List<Poem> items = new ArrayList<>();

    private PoemAdapter adapter;
    private TextView title;
    private LinearLayoutManager lm;
    private String kind, name;
    private int total = -1;
    private int taken;
    private boolean loading;
    private boolean knownTotal;
    /** 转屏重建后要回到的位置，取够条目之前不做滚动，避免滚回顶部重取所有页。 */
    private int restoreTo = -1;

    public static void open(Context ctx, int mode, String name) {
        ctx.startActivity(new Intent(ctx, ListActivity.class)
                .putExtra(KEY_MODE, mode).putExtra(KEY_NAME, name));
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_list);
        int mode = getIntent().getIntExtra(KEY_MODE, MODE_DYNASTY);
        kind = mode == MODE_AUTHOR ? "author" : mode == MODE_TAG ? "tag"
                : mode == MODE_SRC ? "src" : "dynasty";
        name = getIntent().getStringExtra(KEY_NAME);
        title = findViewById(R.id.list_title);
        findViewById(R.id.btn_back).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                finish();
            }
        });

        adapter = new PoemAdapter(items);
        RecyclerView body = findViewById(R.id.list_body);
        lm = new LinearLayoutManager(this);
        body.setLayoutManager(lm);
        body.setAdapter(adapter);
        body.addOnScrollListener(new RecyclerView.OnScrollListener() {
            @Override
            public void onScrolled(RecyclerView rv, int dx, int dy) {
                if (dy > 0 && lm.findLastVisibleItemPosition() >= items.size() - 15) loadMore();
            }
        });

        if (savedInstanceState != null) {
            taken = savedInstanceState.getInt(KEY_TAKEN, 0);
            restoreTo = savedInstanceState.getInt(KEY_SCROLL, -1);
        }

        // 进程被系统回收后恢复进来时仓库可能还没就绪，这里必须挂监听，否则 total 恒为 0 → 永久空表
        if (PoemApp.repo.isFailed()) {
            title.setText(R.string.load_failed);
            return;
        }
        if (!PoemApp.repo.isReady()) {
            title.setText(R.string.loading);
            PoemApp.repo.whenReady(this);
            return;
        }
        start();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        outState.putInt(KEY_TAKEN, taken);
        outState.putInt(KEY_SCROLL, restoreTo >= 0 ? restoreTo : lm.findFirstVisibleItemPosition());
    }

    @Override
    protected void onDestroy() {
        PoemApp.repo.removeReadyListener(this);
        super.onDestroy();
    }

    @Override
    public void onReady() {
        if (isFinishing() || isDestroyed()) return;
        if (!PoemApp.repo.isReady()) {
            title.setText(R.string.load_failed);
            return;
        }
        if (taken == 0) start();
    }

    private void start() {
        PoemApp.repo.bg(new Runnable() {
            @Override
            public void run() {
                // countFacet 也是查库，不能留在 onCreate 的主线程上
                final int n = PoemApp.repo.countFacet(kind, name);
                PoemApp.repo.ui(new Runnable() {
                    @Override
                    public void run() {
                        if (isFinishing() || isDestroyed()) return;
                        total = n;
                        knownTotal = true;
                        title.setText(getString(R.string.list_title, name, Fmt.count(n, "篇")));
                        if (taken > n) {
                            taken = n;
                            restoreTo = -1;
                        }
                        loadMore();
                    }
                });
            }
        });
    }

    private void loadMore() {
        if (loading || !knownTotal || exhausted()) return;
        loading = true;
        final int offset = taken;
        PoemApp.repo.bg(new Runnable() {
            @Override
            public void run() {
                List<Poem> page;
                try {
                    page = PoemApp.repo.byFacet(kind, name, PAGE, offset);
                } catch (Exception e) {
                    page = new ArrayList<>();
                }
                final List<Poem> rows = page;
                PoemApp.repo.ui(new Runnable() {
                    @Override
                    public void run() {
                        loading = false;
                        if (isFinishing() || isDestroyed()) return;
                        if (rows.isEmpty()) {
                            // 空页即终止：count 与 byFacet 口径不一致时也不能在主线程无限递归
                            total = taken;
                            return;
                        }
                        items.addAll(rows);
                        taken += rows.size();
                        adapter.notifyItemRangeInserted(offset, rows.size());
                        settleIfRestoring();
                        // 首页没铺满屏幕就滚不动，也就触发不了后续加载
                        if (offset == 0 && needsPriming()) loadMore();
                    }
                });
            }
        });
    }

    private boolean exhausted() {
        return total >= 0 && taken >= total;
    }

    /** 补页只补到「能滚动」或「够回到原位」，不会把所有页一次拉完。 */
    private boolean needsPriming() {
        int target = Math.max(PAGE, restoreTo + 1);
        return taken < target && taken < total;
    }

    private void settleIfRestoring() {
        if (restoreTo < 0 || taken <= restoreTo) return;
        int anchor = restoreTo;
        restoreTo = -1;
        lm.scrollToPositionWithOffset(anchor, 0);
    }
}
