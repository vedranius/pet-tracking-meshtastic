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
        val openAppIntent = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val stopIntent = PendingIntent.getService(
            context, 0,
            Intent(context, LocationShareService::class.java).setAction(LocationShareService.ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(context, SHARING_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.notification_sharing_title))
            .setContentText(context.getString(R.string.notification_sharing_text))
            .setContentIntent(openAppIntent)
            .addAction(0, context.getString(R.string.notification_action_stop), stopIntent)
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
