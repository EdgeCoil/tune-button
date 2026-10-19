// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager

class App : Application() {
    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(Notify.DONE, "Saved", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "A press saved the current song"
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 60)
        })
        nm.createNotificationChannel(NotificationChannel(Notify.FAILED, "Failed", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "A press could not save the song"
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 250, 150, 250)
        })
        nm.createNotificationChannel(NotificationChannel(Notify.WORK, "Working", NotificationManager.IMPORTANCE_MIN))
        Scanner.register(this)
    }
}
