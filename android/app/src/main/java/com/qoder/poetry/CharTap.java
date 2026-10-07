package com.qoder.poetry;

import android.text.Layout;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.widget.TextView;

/** 正文里点某个字查字典：把触点坐标换算成字符下标。 */
public class CharTap {

    public interface OnChar {
        /** zi 是完整码点的字符串，落在代理对里的生僻字不会被拆成半个。 */
        void onChar(String zi, int index);
    }

    public static void attach(final TextView view, final OnChar cb) {
        if (view == null || cb == null) return;
        final int slop = ViewConfiguration.get(view.getContext()).getScaledTouchSlop();
        view.setOnTouchListener(new View.OnTouchListener() {
            private float downX, downY;

            @Override
            public boolean onTouch(View v, MotionEvent ev) {
                // 不在 DOWN 时认领的话，父 ScrollView 会把事件流拿走，UP 永远收不到；
                // 认领后滚动依然正常，因为父容器会在超过滑动阈值时拦截。
                int action = ev.getActionMasked();
                if (action == MotionEvent.ACTION_DOWN) {
                    downX = ev.getX();
                    downY = ev.getY();
                    return true;
                }
                if (action != MotionEvent.ACTION_UP) return false;
                v.performClick();
                // 拖过阈值就是滚动不是点按，别在手指抬起的地方命中一个字
                if (Math.abs(ev.getX() - downX) > slop || Math.abs(ev.getY() - downY) > slop) {
                    return false;
                }
                return hit((TextView) v, ev.getX(), ev.getY(), slop, cb);
            }
        });
    }

    private static boolean hit(TextView tv, float rx, float ry, int slop, OnChar cb) {
        Layout layout = tv.getLayout();
        CharSequence text = tv.getText();
        if (layout == null || text == null || text.length() == 0) return false;
        float x = rx - tv.getTotalPaddingLeft() + tv.getScrollX();
        float y = ry - tv.getTotalPaddingTop() + tv.getScrollY();
        if (x < 0 || y < 0) return false;
        // 末行下方的空白也归到某一行的垂直范围里，这里按整体高度先挡一道
        if (y > layout.getHeight()) return false;
        int line = layout.getLineForVertical((int) y);
        if (y > layout.getLineBottom(line) || y < layout.getLineTop(line)) return false;
        // getOffsetForHorizontal 会把越界的 x 钳到行尾，不挡住就会命中该行最后一个字
        if (x > layout.getLineRight(line) + slop || x < layout.getLineLeft(line) - slop) {
            return false;
        }
        int off = layout.getOffsetForHorizontal(line, x);
        return pick(text, off - 1, cb) || pick(text, off, cb);
    }

    private static boolean pick(CharSequence text, int i, OnChar cb) {
        if (i < 0 || i >= text.length()) return false;
        char ch = text.charAt(i);
        int start = i;
        if (Character.isLowSurrogate(ch) && i > 0
                && Character.isHighSurrogate(text.charAt(i - 1))) {
            start = i - 1;
        }
        char hi = text.charAt(start);
        char lo = start + 1 < text.length() ? text.charAt(start + 1) : 0;
        // CharSequence 没有 codePointAt，自己按代理对拼出码点
        int cp = Character.isHighSurrogate(hi) && Character.isLowSurrogate(lo)
                ? Character.toCodePoint(hi, lo) : hi;
        int len = Character.charCount(cp);
        if (start + len > text.length()) return false;
        if (!isCjk(cp)) return false;
        cb.onChar(text.subSequence(start, start + len).toString(), start);
        return true;
    }

    /** 按码点判断：兼容表意文字和所有落在代理对里的扩展汉字，正是最需要注音的那批。 */
    private static boolean isCjk(int cp) {
        return (cp >= 0x3400 && cp <= 0x9FFF)        // 统一表意文字 + 扩展 A
                || (cp >= 0xF900 && cp <= 0xFAFF)    // 兼容表意文字
                || cp == 0x3007                      // 〇
                || (cp >= 0x20000 && cp <= 0x2FA1F); // 扩展 B–F 与兼容补充（代理对）
    }
}
