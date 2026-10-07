package com.qoder.poetry;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import java.util.List;

public class FacetAdapter extends RecyclerView.Adapter<FacetAdapter.VH> {

    public interface OnPick {
        void pick(String key);
    }

    private final List<PoemRepository.Facet> data;
    private final OnPick callback;

    public FacetAdapter(List<PoemRepository.Facet> data, OnPick cb) {
        this.data = data;
        callback = cb;
    }

    static class VH extends RecyclerView.ViewHolder {
        final TextView name;
        final TextView count;

        VH(View v) {
            super(v);
            name = v.findViewById(R.id.facet_name);
            count = v.findViewById(R.id.facet_count);
        }
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int type) {
        return new VH(LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_facet, parent, false));
    }

    @Override
    public void onBindViewHolder(@NonNull VH h, int pos) {
        final PoemRepository.Facet f = data.get(pos);
        // 网格按位置循环六色：浅底卡片 + 深色字，滚动时五颜六色
        final android.content.Context ctx = h.itemView.getContext();
        final int hue = pos % Hue.COUNT;
        h.itemView.setBackground(Hue.pressable(ctx, hue, 12));
        h.name.setTextColor(Hue.deep(ctx, hue));
        h.count.setTextColor(Hue.faded(ctx, hue, 170));
        h.name.setText(f.name);
        h.count.setText(ctx.getResources()
                .getString(R.string.count_poems, Fmt.count(f.count, "篇")));
        h.itemView.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                callback.pick(f.name);
            }
        });
    }

    @Override
    public int getItemCount() {
        return data.size();
    }
}
