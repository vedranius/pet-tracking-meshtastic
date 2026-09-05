package com.pawtrack.app

import android.webkit.CookieManager

/** The user signs in through the WebView (MainActivity), which is the only
 * place PawTrack's session cookie gets set — including going through a
 * Cloudflare Access / OTP interstitial first, if the server is set up that
 * way. Rather than re-implement login natively, the background service
 * reads that same cookie out of the shared Android CookieManager and
 * attaches it to its own HTTP/WebSocket requests. Until the user actually
 * logs in through the WebView there's no cookie yet, so those requests will
 * just get 401s — handled as a normal retry case, not an error. */
object CookieBridge {
    fun cookieHeaderFor(url: String): String? {
        val cookie = CookieManager.getInstance().getCookie(url)
        return if (cookie.isNullOrBlank()) null else cookie
    }
}
