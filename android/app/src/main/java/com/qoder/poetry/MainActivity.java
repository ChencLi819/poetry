package com.qoder.poetry;

import android.annotation.SuppressLint;
import android.content.pm.ApplicationInfo;
import android.graphics.Color;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.view.View;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;

import java.util.Locale;

/**
 * 宿主：一个 WebView + 一层语料释放遮罩。
 *
 * 页面、路由、交互全在 assets/web 里；原生只负责三件事——
 * 把 237MB 语料库从 assets 释放出来、给前端提供查库能力、以及诵读（TTS）。
 */
public class MainActivity extends AppCompatActivity
        implements PoemRepository.ReadyListener, Bridge.Host {

    private static final String URL = "file:///android_asset/web/index.html";

    private WebView web;
    private View loading;
    private TextView loadingText;
    private View retry;
    private TextToSpeech tts;
    private boolean ttsReady;
    private boolean canGoBack;
    private boolean pageLoaded;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        loading = findViewById(R.id.loading);
        loadingText = (TextView) findViewById(R.id.loading_text);
        retry = findViewById(R.id.loading_retry);
        retry.setVisibility(View.GONE);

        web = (WebView) findViewById(R.id.web);
        web.setBackgroundColor(Color.parseColor("#F6F1E7"));
        web.setWebViewClient(new WebViewClient());
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(false);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);
        // 页面与它的 js/css 都在 assets 下，同源加载，不放开会影响子资源读取
        s.setAllowFileAccessFromFileURLs(true);
        // 只在可调试包上开 WebView 远程调试；没有 BuildConfig 就用 debuggable 标志判断
        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        web.addJavascriptInterface(
                new Bridge(web, PoemApp.repo, PoemApp.favorites, PoemApp.stats, this), "Android");

        retry.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                retryLoad();
            }
        });

        PoemApp.repo.setProgress(new Db.Progress() {
            @Override
            public void onPercent(int percent) {
                if (isFinishing() || isDestroyed()) return;
                loadingText.setText(getString(R.string.extracting, percent));
            }
        });
        int done = PoemApp.repo.progressPercent();
        if (done > 0) loadingText.setText(getString(R.string.extracting, done));
        PoemApp.repo.whenReady(this);
    }

    @Override
    protected void onDestroy() {
        PoemApp.repo.setProgress(null);
        PoemApp.repo.removeReadyListener(this);
        if (tts != null) {
            tts.shutdown();
            tts = null;
        }
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    private void retryLoad() {
        retry.setVisibility(View.GONE);
        loading.setVisibility(View.VISIBLE);
        loadingText.setText(R.string.loading);
        PoemApp.repo.retry(this, this);
    }

    @Override
    public void onReady() {
        if (PoemApp.repo.isReady()) {
            loading.setVisibility(View.GONE);
            retry.setVisibility(View.GONE);
            if (!pageLoaded) {
                pageLoaded = true;
                web.loadUrl(URL);
            }
            return;
        }
        if (PoemApp.repo.isFailed()) {
            loading.setVisibility(View.VISIBLE);
            String why = PoemApp.repo.errorMessage();
            loadingText.setText(getString(R.string.load_failed_detail,
                    why == null || why.isEmpty() ? getString(R.string.load_failed) : why));
            retry.setVisibility(View.VISIBLE);
        }
    }

    /* -------------------------------------------------------- Bridge.Host */

    @Override
    public void onRoute(int depth, String tab) {
        canGoBack = depth > 0 || (tab != null && !"home".equals(tab));
    }

    @Override
    public void toast(String msg) {
        if (msg != null) Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    @Override
    public void speak(final String text) {
        if (tts == null) {
            tts = new TextToSpeech(getApplicationContext(), new TextToSpeech.OnInitListener() {
                @Override
                public void onInit(int status) {
                    ttsReady = status == TextToSpeech.SUCCESS
                            && tts.setLanguage(Locale.SIMPLIFIED_CHINESE) != TextToSpeech.LANG_MISSING_DATA
                            && tts.setLanguage(Locale.SIMPLIFIED_CHINESE) != TextToSpeech.LANG_NOT_SUPPORTED;
                    if (ttsReady) doSpeak(text);
                    else Toast.makeText(MainActivity.this, R.string.tts_missing, Toast.LENGTH_SHORT).show();
                }
            });
            return;
        }
        if (ttsReady) doSpeak(text);
    }

    private void doSpeak(String text) {
        if (tts == null || text == null || text.isEmpty()) return;
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "poem");
    }

    /* -------------------------------------------------------------- 返回键 */

    @Override
    public void onBackPressed() {
        // 前端有堆叠页面或不在首页时，先让前端自己退一层
        if (canGoBack && web != null) {
            web.evaluateJavascript("__back()", null);
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onSaveInstanceState(@NonNull Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    protected void onRestoreInstanceState(@NonNull Bundle savedInstanceState) {
        super.onRestoreInstanceState(savedInstanceState);
        if (web != null) web.restoreState(savedInstanceState);
    }
}
