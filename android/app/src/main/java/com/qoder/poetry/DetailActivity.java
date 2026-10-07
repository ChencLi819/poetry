package com.qoder.poetry;

import android.content.Context;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

/** 单篇诗文：原文（生僻字注音）+ 译文 / 注释 / 简析 / 背景 / 赏析。 */
public class DetailActivity extends AppCompatActivity implements PoemRepository.ReadyListener {

    private static final String KEY_ID = "poem_id";

    private LinearLayout sections;
    private TextView titleView, metaView, bodyView, hintView, barTitle;
    private ImageView favButton;
    private Poem poem;

    public static void open(Context ctx, String id) {
        ctx.startActivity(new Intent(ctx, DetailActivity.class).putExtra(KEY_ID, id));
    }

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_detail);
        titleView = findViewById(R.id.det_title);
        metaView = findViewById(R.id.det_meta);
        bodyView = findViewById(R.id.det_text);
        hintView = findViewById(R.id.det_pinyin_hint);
        barTitle = findViewById(R.id.bar_title);
        sections = findViewById(R.id.det_sections);
        favButton = findViewById(R.id.btn_fav);
        findViewById(R.id.btn_back).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                finish();
            }
        });
        favButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (poem == null) return;
                PoemApp.favorites.toggle(poem.id);
                syncFav();
            }
        });
        PoemApp.repo.whenReady(this);
    }

    @Override
    protected void onDestroy() {
        PoemApp.repo.removeReadyListener(this);
        super.onDestroy();
    }

    /** byId 取的是整篇长文，含 FULL 的十来个字段，不能在主线程查。 */
    @Override
    public void onReady() {
        if (PoemApp.repo.isFailed()) {
            showLoadFailed();
            return;
        }
        if (!PoemApp.repo.isReady()) return;
        final String id = getIntent().getStringExtra(KEY_ID);
        PoemApp.repo.bg(new Runnable() {
            @Override
            public void run() {
                final Poem p = PoemApp.repo.byId(id);
                PoemApp.repo.ui(new Runnable() {
                    @Override
                    public void run() {
                        if (isFinishing() || isDestroyed()) return;
                        if (p == null) {
                            // 库是好的，只是这篇不存在——这才是要退出的情形
                            Toast.makeText(DetailActivity.this, R.string.poem_missing,
                                    Toast.LENGTH_SHORT).show();
                            finish();
                            return;
                        }
                        bind(p);
                    }
                });
            }
        });
    }

    private void showLoadFailed() {
        String why = PoemApp.repo.errorMessage();
        barTitle.setText(R.string.load_failed);
        metaView.setText(getString(R.string.load_failed_reason,
                why == null || why.isEmpty() ? getString(R.string.load_failed) : why));
        hintView.setVisibility(View.GONE);
    }

    private void bind(Poem p) {
        poem = p;
        barTitle.setText(p.title);
        titleView.setText(p.title);
        metaView.setText((p.source.isEmpty() ? p.author : p.source) + " · " + p.dynasty);
        bodyView.setText(Ruby.annotate(p.text, p.pinyin,
                ContextCompat.getColor(this, R.color.accent)));
        hintView.setVisibility(p.pinyin.isEmpty() ? View.GONE : View.VISIBLE);
        CharTap.attach(bodyView, new CharTap.OnChar() {
            @Override
            public void onChar(String zi, int index) {
                ZiSheet.show(DetailActivity.this, zi);
            }
        });
        buildTags(p);
        buildSections(p);
        syncFav();
    }

    private void buildTags(Poem p) {
        ViewGroup tags = findViewById(R.id.det_tags);
        LayoutInflater lf = LayoutInflater.from(this);
        int shown = 0;
        for (String t : p.tags) {
            if (shown >= 6) break;
            TextView chip = (TextView) lf.inflate(R.layout.item_tag, tags, false);
            chip.setText(t);
            chip.setBackground(Hue.soft(this, shown, 6));
            chip.setTextColor(Hue.deep(this, shown));
            tags.addView(chip);
            shown++;
        }
        tags.setVisibility(shown == 0 ? View.GONE : View.VISIBLE);
    }

    private void buildSections(Poem p) {
        sections.removeAllViews();
        addSection(R.string.section_yiwen, p.yiwen, Hue.PINE);
        addSection(R.string.section_zhushi, p.zhushi, Hue.INK);
        addSection(R.string.section_jianxi, p.jianxi, Hue.LOTUS);
        addSection(R.string.section_beijing, p.beijing, Hue.GOLD);
        addSection(R.string.section_shangxi, p.shangxi, Hue.CRIMSON);
        if (sections.getChildCount() == 0) {
            addSection(R.string.section_note, getString(R.string.no_annotation), Hue.ROSE);
        }
    }

    private void addSection(int titleRes, String body, int hue) {
        if (body == null || body.trim().isEmpty()) return;
        View v = LayoutInflater.from(this).inflate(R.layout.item_section, sections, false);
        TextView titleView = v.findViewById(R.id.sec_title);
        titleView.setText(titleRes);
        titleView.setTextColor(Hue.deep(this, hue));
        v.findViewById(R.id.sec_bar).setBackgroundTintList(
                ColorStateList.valueOf(Hue.main(this, hue)));
        final TextView bodyView = v.findViewById(R.id.sec_body);
        bodyView.setText(body);
        CharTap.attach(bodyView, new CharTap.OnChar() {
            @Override
            public void onChar(String zi, int index) {
                ZiSheet.show(DetailActivity.this, zi);
            }
        });
        sections.addView(v);
    }

    private void syncFav() {
        if (poem == null) return;
        boolean on = PoemApp.favorites.has(poem.id);
        favButton.setSelected(on);
        favButton.setContentDescription(getString(on ? R.string.tab_fav : R.string.fav_add));
    }
}
