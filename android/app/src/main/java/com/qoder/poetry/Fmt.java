package com.qoder.poetry;

import java.util.Locale;

/** 计数文案：过万压成「万」，例如 345990 → 34.6万篇，4102 → 4102 篇。 */
public class Fmt {

    public static String count(long n, String unit) {
        if (n < 10000) return n + " " + unit;
        String s = String.format(Locale.CHINA, "%.1f", n / 10000.0);
        if (s.endsWith(".0")) s = s.substring(0, s.length() - 2);
        return s + "万" + unit;
    }
}
