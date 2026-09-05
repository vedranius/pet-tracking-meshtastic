package com.pawtrack.app

import android.content.Context

/** Mirrors backend/app/services/mesh_manager.py's _EVENT_TEMPLATES and
 * frontend/js/eventText.js — the server sends the alert's `message` as a
 * "::"-delimited template id + args (e.g. "low_battery::Roxy::15") so each
 * client renders it in its own language rather than the server baking in
 * one fixed language. Android's string resources (values / values-hr)
 * supply the actual text; this just does the same parsing/dispatch. */
object EventText {
    fun render(context: Context, eventType: String?, message: String?): String {
        if (message == null) return ""
        val parts = message.split("::")
        return try {
            when (eventType) {
                "low_battery" -> context.getString(R.string.event_low_battery, parts[1], parts[2])
                "geofence_enter" -> context.getString(R.string.event_geofence_enter, parts[1], parts[2])
                "geofence_exit" -> context.getString(R.string.event_geofence_exit, parts[1], parts[2])
                "geofence_exit_update" -> context.getString(R.string.event_geofence_exit_update, parts[1], parts[2])
                "offline" -> context.getString(R.string.event_offline, parts[1], parts[2])
                "ring_sent" -> context.getString(R.string.event_ring_sent, parts[1])
                else -> message
            }
        } catch (e: IndexOutOfBoundsException) {
            message
        }
    }
}
