package com.qoder.poetry;

import android.graphics.Canvas;
import android.graphics.Paint;
import android.text.SpannableStringBuilder;
import android.text.Spanned;

/**
 * 生僻字头顶注音。
 * 注音串格式为 "utf16下标:读音" 空格分隔，下标由构建脚本按正文算好，
 * 因此运行时只做定位，不会像"按顺序取音节"那样错位。
 */
public class Ruby {

    /** 拼音字号相对正文的比例与抬升高度，getSize 和 draw 必须用同一组数。 */
    private static final float SIZE_RATIO = 0.46f;
    private static final float RAISE_RATIO = 0.86f;

    public static class Span extends android.text.style.ReplacementSpan {
        private final String py;
        private final int color;
        private Paint cache;

        Span(String py, int color) {
            this.py = py;
            this.color = color;
        }

        /**
         * 行高要按拼音实际需要的高度撑开：只靠 lineSpacingMultiplier 的话，多出来的间距
         * 是加在本行下方的，救不了首行——首行拼音会越出顶边被裁掉。
         */
        @Override
        public int getSize(Paint paint, CharSequence text, int start, int end,
                           Paint.FontMetricsInt fm) {
            int w = (int) Math.ceil(paint.measureText(text, start, end));
            int min = (int) Math.ceil(paint.measureText("中"));
            if (fm != null && py != null && !py.isEmpty()) {
                // 拼音字体的字形高度按同一比例从正文的 ascent 折算，不额外造 Paint
                int need = (int) Math.ceil(paint.getTextSize() * RAISE_RATIO
                        + -fm.ascent * SIZE_RATIO);
                if (-fm.top < need) fm.top = -need;
                if (-fm.ascent < need) fm.ascent = -need;
            }
            return Math.max(w, min);
        }

        @Override
        public void draw(Canvas canvas, CharSequence text, int start, int end,
                         float x, int top, int y, int bottom, Paint paint) {
            canvas.drawText(text, start, end, x, y, paint);
            if (py == null || py.isEmpty()) return;
            float size = paint.getTextSize() * SIZE_RATIO;
            if (cache == null) {
                cache = new Paint(paint);
                cache.setAntiAlias(true);
                cache.setColor(color);
                cache.setTextSize(size);
            }
            float w = paint.measureText(text, start, end);
            canvas.drawText(py, 0, py.length(),
                    x + (w - cache.measureText(py)) / 2f,
                    y - paint.getTextSize() * RAISE_RATIO, cache);
        }
    }

    public static CharSequence annotate(String text, String spec, int color) {
        if (text == null || text.isEmpty() || spec == null || spec.isEmpty()) return text;
        SpannableStringBuilder sb = new SpannableStringBuilder(text);
        int n = text.length();
        for (String item : spec.split(" ")) {
            int colon = item.indexOf(':');
            if (colon <= 0) continue;
            int at;
            try {
                at = Integer.parseInt(item.substring(0, colon));
            } catch (NumberFormatException e) {
                continue;
            }
            if (at < 0 || at >= n) continue;
            int start = at;
            // 下标可能落在低代理上，回退到码点起始，别把一个码点拆成两半
            if (Character.isLowSurrogate(text.charAt(start)) && start > 0
                    && Character.isHighSurrogate(text.charAt(start - 1))) {
                start--;
            }
            int end = Math.min(n, start + Character.charCount(text.codePointAt(start)));
            if (end <= start || sb.getSpans(start, end, Object.class).length > 0) continue;
            sb.setSpan(new Span(item.substring(colon + 1), color),
                    start, end, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        return sb;
    }
}
