package com.qoder.poetry;

public class Zi {

    public final String zi;
    public final String pinyin;
    public final String traditional;
    public final String radical;
    public final int strokes;
    public final String senses;
    public final String gloss;
    public final String form;
    public final String evidence;
    public final String phrase;

    Zi(String zi, String pinyin, String traditional, String radical, int strokes,
       String senses, String gloss, String form, String evidence, String phrase) {
        this.zi = zi;
        this.pinyin = pinyin;
        this.traditional = traditional;
        this.radical = radical;
        this.strokes = strokes;
        this.senses = senses;
        this.gloss = gloss;
        this.form = form;
        this.evidence = evidence;
        this.phrase = phrase;
    }

    public boolean isEmpty() {
        return senses.isEmpty() && gloss.isEmpty() && evidence.isEmpty() && phrase.isEmpty();
    }
}
