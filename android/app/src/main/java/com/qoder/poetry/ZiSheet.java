package com.qoder.poetry;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.FragmentActivity;

import com.google.android.material.bottomsheet.BottomSheetDialogFragment;

/** 点正文里的字，弹出该字的字典条目。 */
public class ZiSheet extends BottomSheetDialogFragment {

    private static final String ARG = "zi";

    @NonNull
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle saved) {
        return inflater.inflate(R.layout.sheet_zi, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle saved) {
        final String zi = requireArguments().getString(ARG, "");
        ((TextView) view.findViewById(R.id.zi_char)).setText(zi);
        // 先按「什么都没有」铺好骨架，查完再填，避免主线程查库
        fill(view, null);
        if (!PoemApp.repo.isReady()) return;
        PoemApp.repo.bg(new Runnable() {
            @Override
            public void run() {
                final Zi z = PoemApp.repo.zi(zi);
                PoemApp.repo.ui(new Runnable() {
                    @Override
                    public void run() {
                        View root = getView();
                        if (!isAdded() || root == null) return;
                        fill(root, z);
                    }
                });
            }
        });
    }

    private static void fill(View root, @Nullable Zi z) {
        boolean found = z != null && !z.isEmpty();
        bind(root, R.id.zi_py, null, z == null ? "" : z.pinyin);
        bind(root, R.id.zi_meta, null, meta(z));
        bind(root, R.id.zi_form, null, z == null ? "" : z.form);
        bind(root, R.id.zi_senses, R.id.zi_senses_label, z == null ? "" : z.senses);
        bind(root, R.id.zi_gloss, R.id.zi_gloss_label, z == null ? "" : z.gloss);
        bind(root, R.id.zi_evidence, R.id.zi_ev_label, z == null ? "" : z.evidence);
        bind(root, R.id.zi_phrase, R.id.zi_phrase_label, z == null ? "" : z.phrase);
        root.findViewById(R.id.zi_empty).setVisibility(found ? View.GONE : View.VISIBLE);
    }

    private static String meta(Zi z) {
        if (z == null) return "";
        StringBuilder sb = new StringBuilder();
        if (!z.radical.isEmpty()) sb.append("部首 ").append(z.radical);
        if (z.strokes > 0) {
            if (sb.length() > 0) sb.append(" · ");
            sb.append(z.strokes).append("画");
        }
        if (!z.traditional.isEmpty() && !z.traditional.equals(z.zi)) {
            if (sb.length() > 0) sb.append(" · ");
            sb.append("繁体 ").append(z.traditional);
        }
        return sb.toString();
    }

    /** 值为空时把标签和内容一起藏掉，避免出现空标题。 */
    private static void bind(View root, int bodyId, @Nullable Integer labelId, String value) {
        View body = root.findViewById(bodyId);
        boolean has = value != null && !value.trim().isEmpty();
        body.setVisibility(has ? View.VISIBLE : View.GONE);
        if (has) ((TextView) body).setText(value);
        if (labelId != null) {
            root.findViewById(labelId).setVisibility(has ? View.VISIBLE : View.GONE);
        }
    }

    /** 参数是完整码点的字符串：生僻字常落在代理对里，用 char 会拆坏。 */
    public static void show(FragmentActivity activity, String zi) {
        if (activity == null || zi == null || zi.isEmpty()) return;
        ZiSheet sheet = new ZiSheet();
        Bundle args = new Bundle();
        args.putString(ARG, zi);
        sheet.setArguments(args);
        sheet.show(activity.getSupportFragmentManager(), "zi");
    }
}
