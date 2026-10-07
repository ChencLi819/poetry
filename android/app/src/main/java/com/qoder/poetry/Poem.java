package com.qoder.poetry;

public class Poem {

    public String id = "";
    public int ord;
    public String title = "";
    public String author = "";
    public String dynasty = "";
    public String text = "";
    public String preview = "";
    public String pinyin = "";
    public String[] tags = new String[0];
    public String yiwen = "";
    public String zhushi = "";
    public String beijing = "";
    public String jianxi = "";
    public String shangxi = "";
    public String source = "";

    /**
     * 列表要直接铺全文，所以 LIGHT 带上正文 tx（第 8 列，与 FULL 对齐）。
     * 只省掉译文注释这些长字段；一页 20 篇的正文量完全可以接受。
     */
    public static final String LIGHT = "id, ord, ti, au, dy, pv, py, tg, tx";
    public static final String FULL = "id, ord, ti, au, dy, pv, py, tg, tx, yw, zs, bj, jx, sx, src";
}
