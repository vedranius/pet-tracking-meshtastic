package com.pawtrack.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

/** Restarts location sharing after a reboot, if a server is configured —
 * otherwise a phone restart would silently stop sharing until the user
 * happens to reopen the app. There's no "was it enabled" check here since
 * sharing has no user-facing on/off switch at all — only an admin can turn
 * it off, server-side. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = PrefsRepository(context)
        if (!prefs.serverUrl.isNullOrBlank()) {
            ContextCompat.startForegroundService(context, Intent(context, LocationShareService::class.java))
        }
    }
}
