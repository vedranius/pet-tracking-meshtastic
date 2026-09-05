package com.pawtrack.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

/** Restarts location sharing after a reboot, if the user had it turned on
 * and a server is configured — otherwise a phone restart would silently
 * stop sharing until the user happens to reopen the app. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = PrefsRepository(context)
        if (prefs.sharingEnabled && !prefs.serverUrl.isNullOrBlank()) {
            ContextCompat.startForegroundService(context, Intent(context, LocationShareService::class.java))
        }
    }
}
