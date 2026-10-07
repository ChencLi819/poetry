package com.qoder.poetry;

import android.content.Context;
import android.util.AttributeSet;
import android.view.View;
import android.view.ViewGroup;

/**
 * 标签行：宽度放不下时自动折到下一行。
 * 与 LinearLayout 不同，这里按 MarginLayoutParams 计算间距，
 * 因为 item_tag 自带 layout_marginRight。
 */
public class TagFlowLayout extends ViewGroup {

    private final int lineGap;

    public TagFlowLayout(Context context, AttributeSet attrs) {
        super(context, attrs);
        lineGap = Math.round(context.getResources().getDisplayMetrics().density * 7);
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        int width = MeasureSpec.getSize(widthMeasureSpec);
        int lineW = 0, lineH = 0, total = 0;
        for (int i = 0; i < getChildCount(); i++) {
            View child = getChildAt(i);
            if (child.getVisibility() == GONE) continue;
            measureChildWithMargins(child, widthMeasureSpec, 0, heightMeasureSpec, 0);
            MarginLayoutParams lp = (MarginLayoutParams) child.getLayoutParams();
            int w = child.getMeasuredWidth() + lp.leftMargin + lp.rightMargin;
            int h = child.getMeasuredHeight() + lp.topMargin + lp.bottomMargin;
            if (lineW > 0 && lineW + w > width) {
                total += lineH + lineGap;
                lineW = 0;
                lineH = 0;
            }
            lineW += w;
            lineH = Math.max(lineH, h);
        }
        setMeasuredDimension(width, resolveSize(total + lineH, heightMeasureSpec));
    }

    @Override
    protected void onLayout(boolean changed, int l, int t, int r, int b) {
        int width = r - l;
        int x = 0, y = 0, lineH = 0;
        for (int i = 0; i < getChildCount(); i++) {
            View child = getChildAt(i);
            if (child.getVisibility() == GONE) continue;
            MarginLayoutParams lp = (MarginLayoutParams) child.getLayoutParams();
            int w = child.getMeasuredWidth() + lp.leftMargin + lp.rightMargin;
            int h = child.getMeasuredHeight() + lp.topMargin + lp.bottomMargin;
            if (x > 0 && x + w > width) {
                y += lineH + lineGap;
                x = 0;
                lineH = 0;
            }
            child.layout(x + lp.leftMargin, y + lp.topMargin,
                    x + lp.leftMargin + child.getMeasuredWidth(),
                    y + lp.topMargin + child.getMeasuredHeight());
            x += w;
            lineH = Math.max(lineH, h);
        }
    }

    @Override
    protected LayoutParams generateDefaultLayoutParams() {
        return new MarginLayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT);
    }

    @Override
    public LayoutParams generateLayoutParams(AttributeSet attrs) {
        return new MarginLayoutParams(getContext(), attrs);
    }

    @Override
    protected LayoutParams generateLayoutParams(LayoutParams p) {
        return new MarginLayoutParams(p);
    }
}
