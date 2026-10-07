package com.qoder.poetry;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import java.util.List;

public class PoemAdapter extends RecyclerView.Adapter<PoemAdapter.VH> {

    private List<Poem> items;

    public PoemAdapter(List<Poem> items) {
        this.items = items;
    }

    public void setItems(List<Poem> next) {
        items = next;
        notifyDataSetChanged();
    }

    static class VH extends RecyclerView.ViewHolder {
        final TextView title;
        final TextView meta;
        final TextView preview;

        VH(View v) {
            super(v);
            title = v.findViewById(R.id.row_title);
            meta = v.findViewById(R.id.row_meta);
            preview = v.findViewById(R.id.row_preview);
        }
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int type) {
        View v = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_poem, parent, false);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH h, int pos) {
        final Poem p = items.get(pos);
        h.title.setText(p.title);
        h.meta.setText(p.author + " · " + p.dynasty);
        h.preview.setText(p.preview);
        h.itemView.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                DetailActivity.open(v.getContext(), p.id);
            }
        });
    }

    @Override
    public int getItemCount() {
        return items.size();
    }
}
