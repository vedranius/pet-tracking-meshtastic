package com.pawtrack.app

import android.app.Application

class PawTrackApp : Application() {
    override fun onCreate() {
        super.onCreate()
        NotificationHelper.createChannels(this)
    }
}
