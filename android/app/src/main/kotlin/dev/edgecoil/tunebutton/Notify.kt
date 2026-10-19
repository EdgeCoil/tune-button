// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent

object Notify {
    const val DONE = "done"
    const val FAILED = "failed"
    const val WORK = "work"
    const val WORK_ID = 1

    fun show(ctx: Context, ok: Boolean, title: String, text: String) {
        val open = PendingIntent.getActivity(
            ctx, 0, Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        val n = Notification.Builder(ctx, if (ok) DONE else FAILED)
            .setSmallIcon(if (ok) android.R.drawable.star_on else android.R.drawable.stat_notify_error)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setTimeoutAfter(if (ok) 15_000 else 120_000)
            .build()
        // One notification per outcome, replaced by the next press.
        try {
            ctx.getSystemService(NotificationManager::class.java).notify(if (ok) 2 else 3, n)
        } catch (e: SecurityException) { /* notifications not permitted */ }
    }

    fun working(ctx: Context): Notification = Notification.Builder(ctx, WORK)
        .setSmallIcon(android.R.drawable.ic_media_play)
        .setContentTitle("Saving to Spotify…")
        .build()
}
