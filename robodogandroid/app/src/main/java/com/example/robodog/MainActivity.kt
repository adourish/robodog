package com.unclebulgaria.robodog

import android.os.Bundle
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContentView(R.layout.activity_main)

        val mWebView = findViewById<WebView>(R.id.webview)
        val webSettings = mWebView.settings
        webSettings.javaScriptEnabled = true
        webSettings.allowContentAccess = true
        webSettings.domStorageEnabled = true
        

        mWebView.loadUrl("https://adourish.github.io/robodog/robodog/dist/")
    }
}