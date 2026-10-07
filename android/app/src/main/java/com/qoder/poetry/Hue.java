package com.qoder.poetry;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;

import androidx.core.content.ContextCompat;
import androidx.core.graphics.ColorUtils;

/** 分类色板：胭脂 / 松绿 / 青黛 / 藕荷 / 缃 / 绛，每色三档——主色、浅底、深字。 */
public class Hue {

    public static final int ROSE = 0, PINE = 1, INK = 2, LOTUS = 3, GOLD = 4, CRIMSON = 5;
    public static final int COUNT = 6;

    private static final int[][] SET = {
            {R.color.palette_rose, R.color.palette_rose_bg, R.color.palette_rose_deep},
            {R.color.palette_pine, R.color.palette_pine_bg, R.color.palette_pine_deep},
            {R.color.palette_ink, R.color.palette_ink_bg, R.color.palette_ink_deep},
            {R.color.palette_lotus, R.color.palette_lotus_bg, R.color.palette_lotus_deep},
            {R.color.palette_gold, R.color.palette_gold_bg, R.color.palette_gold_deep},
            {R.color.palette_crimson, R.color.palette_crimson_bg, R.color.palette_crimson_deep},
    };

    public static int main(Context c, int hue) {
        return ContextCompat.getColor(c, SET[((hue % COUNT) + COUNT) % COUNT][0]);
    }

    public static int deep(Context c, int hue) {
        return ContextCompat.getColor(c, SET[((hue % COUNT) + COUNT) % COUNT][2]);
    }

    public static int faded(Context c, int hue, int alpha) {
        return ColorUtils.setAlphaComponent(deep(c, hue), alpha);
    }

    private static GradientDrawable shape(Context c, int hue, float radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(ContextCompat.getColor(c, SET[((hue % COUNT) + COUNT) % COUNT][1]));
        d.setCornerRadius(radiusDp * c.getResources().getDisplayMetrics().density);
        return d;
    }

    /** 浅底圆角块（标签、色章）。 */
    public static GradientDrawable soft(Context c, int hue, float radiusDp) {
        return shape(c, hue, radiusDp);
    }

    /** 浅底圆角 + 按压水波（分类卡）。 */
    public static RippleDrawable pressable(Context c, int hue, float radiusDp) {
        GradientDrawable mask = shape(c, hue, radiusDp);
        mask.setColor(0xFFFFFFFF);
        return new RippleDrawable(
                ColorStateList.valueOf(ContextCompat.getColor(c, R.color.ripple)),
                shape(c, hue, radiusDp), mask);
    }
}
