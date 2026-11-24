package com.custom.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private WebView webView;
    private static final String ROOT_URL = "file:///android_asset/web/index.html";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return false;
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                // Clear the back stack whenever returning to the home screen
                if (url != null && (url.endsWith("index.html") || url.equals(ROOT_URL))) {
                    view.clearHistory();
                }
            }
        });

        webView.loadUrl(ROOT_URL);
        setContentView(webView);
    }

    @Override
    public void onBackPressed() {
        String currentUrl = (webView != null) ? webView.getUrl() : null;
        boolean isHome = (currentUrl == null || currentUrl.endsWith("index.html") || currentUrl.equals(ROOT_URL));

        if (isHome || !webView.canGoBack()) {
            showExitDialog();
        } else {
            webView.goBack();
        }
    }

    private void showExitDialog() {
        new AlertDialog.Builder(this)
            .setTitle("Exit App")
            .setMessage("Are you sure you want to exit?")
            .setPositiveButton("Exit", new DialogInterface.OnClickListener() {
                @Override
                public void onClick(DialogInterface dialog, int which) {
                    finish();
                }
            })
            .setNegativeButton("Cancel", null)
            .show();
    }
}
