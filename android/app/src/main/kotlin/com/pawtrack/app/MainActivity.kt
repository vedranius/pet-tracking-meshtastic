package com.pawtrack.app

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.net.http.SslError
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.addCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.pawtrack.app.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: PrefsRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = PrefsRepository(this)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        val url = prefs.serverUrl
        if (url.isNullOrBlank()) {
            startActivity(Intent(this, SetupActivity::class.java))
            finish()
            return
        }

        setupWebView(url)
        binding.retryButton.setOnClickListener { loadServer(url) }

        onBackPressedDispatcher.addCallback(this) {
            if (binding.webView.canGoBack()) binding.webView.goBack() else finish()
        }

        if (prefs.sharingEnabled) startSharingService()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView(url: String) {
        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(binding.webView, true)

        binding.webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            // A few pixels of pinch-zoom room helps on small phones; the web
            // app itself is already responsive so this is a safety net, not
            // load-bearing.
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
        }

        binding.webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, loadedUrl: String, favicon: Bitmap?) {
                binding.progressBar.visibility = android.view.View.VISIBLE
                binding.errorView.visibility = android.view.View.GONE
            }

            override fun onPageFinished(view: WebView, loadedUrl: String) {
                binding.progressBar.visibility = android.view.View.GONE
                cookieManager.flush()
            }

            // Deliberately not restricted to the configured host: a
            // Cloudflare Access / Zero Trust login (OTP) flow redirects
            // through a *.cloudflareaccess.com page before coming back to
            // the app's own domain, and that whole handshake needs to
            // happen inside this WebView to work at all.
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val scheme = request.url.scheme
                if (scheme == "http" || scheme == "https") return false
                return try {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                    true
                } catch (e: android.content.ActivityNotFoundException) {
                    true
                }
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) showError(url)
            }

            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
                // Self-hosted servers often sit behind self-signed certs on
                // a bare LAN IP during initial setup — fail closed by
                // default (cancel) rather than silently trusting anything,
                // same posture a normal browser takes.
                handler.cancel()
                showError(url)
            }
        }

        loadServer(url)
    }

    private fun loadServer(url: String) {
        binding.errorView.visibility = android.view.View.GONE
        binding.webView.visibility = android.view.View.VISIBLE
        binding.webView.loadUrl(url)
    }

    private fun showError(url: String) {
        binding.webView.visibility = android.view.View.GONE
        binding.progressBar.visibility = android.view.View.GONE
        binding.errorView.visibility = android.view.View.VISIBLE
        binding.errorText.text = getString(R.string.webview_load_error, url)
    }

    private fun startSharingService() {
        ContextCompat.startForegroundService(this, Intent(this, LocationShareService::class.java))
    }

    private fun stopSharingService() {
        startService(Intent(this, LocationShareService::class.java).setAction(LocationShareService.ACTION_STOP))
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onPrepareOptionsMenu(menu: Menu): Boolean {
        menu.findItem(R.id.action_toggle_sharing).setTitle(
            if (prefs.sharingEnabled) R.string.menu_stop_sharing else R.string.menu_start_sharing
        )
        return super.onPrepareOptionsMenu(menu)
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_toggle_sharing -> {
                if (prefs.sharingEnabled) stopSharingService() else startSharingService()
                true
            }
            R.id.action_change_server -> {
                AlertDialog.Builder(this)
                    .setMessage(R.string.change_server_confirm)
                    .setPositiveButton(android.R.string.ok) { _, _ ->
                        stopSharingService()
                        prefs.serverUrl = null
                        prefs.onboardingDone = false
                        CookieManager.getInstance().removeAllCookies(null)
                        startActivity(Intent(this, SetupActivity::class.java))
                        finish()
                    }
                    .setNegativeButton(android.R.string.cancel, null)
                    .show()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }
}
