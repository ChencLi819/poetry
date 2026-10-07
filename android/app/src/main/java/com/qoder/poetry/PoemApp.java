package com.qoder.poetry;

import android.app.Application;

public class PoemApp extends Application {

    public static PoemRepository repo;
    public static Favorites favorites;
    public static Stats stats;

    @Override
    public void onCreate() {
        super.onCreate();
        favorites = new Favorites(this);
        stats = new Stats(this);
        repo = new PoemRepository();
        repo.loadAsync(this);
    }
}
