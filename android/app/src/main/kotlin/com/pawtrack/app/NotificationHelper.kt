package com.pawtrack.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import kotlin.math.abs

object NotificationHelper {
    const val SHARING_CHANNEL_ID = "pawtrack_sharing"
    const val ALERTS_CHANNEL_ID = "pawtrack_alerts"
    const val SHARING_NOTIFICATION_ID = 1
    private const val ALERT_NOTIFICATION_BASE_ID = 1000

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)

        val sharing = NotificationChannel(
            SHARING_CHANNEL_ID,
            context.getString(R.string.notification_channel_sharing_name),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = context.getString(R.string.notification_channel_sharing_desc)
        }

        val alerts = NotificationChannel(
            ALERTS_CHANNEL_ID,
            context.getString(R.string.notification_channel_alerts_name),
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = context.getString(R.string.notification_channel_alerts_desc)
        }

        manager.createNotificationChannel(sharing)
        manager.createNotificationChannel(alerts)
    }

    fun buildSharingNotification(context: Context): android.app.Notification {
        // Deliberately no "stop sharing" action here — there's no
        // user-facing way to turn this off at all, only an admin can
        // (server-side). The notification exists for transparency
        // (required for a location-type foreground service) and as a
        // shortcut back into the app, not as a control surface.
        val openAppIntent = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(context, SHARING_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.notification_sharing_title))
            .setContentText(context.getString(R.string.notification_sharing_text))
            .setContentIntent(openAppIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    fun showAlert(context: Context, eventType: String, text: String) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val notification = NotificationCompat.Builder(context, ALERTS_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        manager.notify(ALERT_NOTIFICATION_BASE_ID + abs(eventType.hashCode()) % 1000, notification)
    }
}
