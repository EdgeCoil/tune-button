// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.Manifest
import android.app.PendingIntent
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build

/**
 * The background scan. It is handed to the system with a PendingIntent, so the system keeps
 * scanning (hardware-filtered on our manufacturer-data prefix) and starts PressReceiver even when
 * the app process is dead.
 */
object Scanner {
    const val ACTION = "dev.edgecoil.tunebutton.PRESS"

    fun canScan(ctx: Context): Boolean {
        val perm = if (Build.VERSION.SDK_INT >= 31) Manifest.permission.BLUETOOTH_SCAN else Manifest.permission.ACCESS_FINE_LOCATION
        return ctx.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED
    }

    private fun pendingIntent(ctx: Context): PendingIntent = PendingIntent.getBroadcast(
        ctx, 1, Intent(ctx, PressReceiver::class.java).setAction(ACTION),
        // Mutable: the system adds the scan results as extras.
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
    )

    /** (Re)registers the scan. Returns a problem description, or null when scanning. */
    @Suppress("MissingPermission")
    fun register(ctx: Context): String? {
        val device = Store(ctx).device ?: return "No device paired"
        if (!canScan(ctx)) return "Bluetooth scan permission not granted"
        val adapter = ctx.getSystemService(BluetoothManager::class.java)?.adapter ?: return "No Bluetooth"
        if (!adapter.isEnabled) return "Bluetooth is off"
        val scanner = adapter.bluetoothLeScanner ?: return "Bluetooth is off"
        val pi = pendingIntent(ctx)
        try { scanner.stopScan(pi) } catch (e: Exception) { }
        val prefix = Packet.filterPrefix(device.id)
        val filter = ScanFilter.Builder()
            .setManufacturerData(Packet.COMPANY_ID, prefix, ByteArray(prefix.size) { 0xFF.toByte() })
            .build()
        val settings = ScanSettings.Builder()
            .setScanMode(Store(ctx).scanMode)
            .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
            .setReportDelay(0)
            .build()
        val rc = scanner.startScan(listOf(filter), settings, pi)
        return if (rc == 0) null else "startScan failed ($rc)"
    }
}
