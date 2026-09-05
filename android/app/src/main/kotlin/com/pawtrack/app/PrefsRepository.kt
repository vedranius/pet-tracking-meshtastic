package com.pawtrack.app

import android.content.Context
import android.content.SharedPreferences

/** Thin wrapper around SharedPreferences for the two bits of state this app
 * needs to remember: which PawTrack server to talk to, and whether the user
 * has turned background location sharing on or off. */
class PrefsRepository(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("pawtrack_prefs", Context.MODE_PRIVATE)

    var serverUrl: String?
        get() = prefs.getString(KEY_SERVER_URL, null)
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value).apply()

    var sharingEnabled: Boolean
        get() = prefs.getBoolean(KEY_SHARING_ENABLED, true)
        set(value) = prefs.edit().putBoolean(KEY_SHARING_ENABLED, value).apply()

    var onboardingDone: Boolean
        get() = prefs.getBoolean(KEY_ONBOARDING_DONE, false)
        set(value) = prefs.edit().putBoolean(KEY_ONBOARDING_DONE, value).apply()

    companion object {
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_SHARING_ENABLED = "sharing_enabled"
        private const val KEY_ONBOARDING_DONE = "onboarding_done"
    }
}
