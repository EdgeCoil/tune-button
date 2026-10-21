// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.UUID

/**
 * Pairing (protocol/spec.md): find the device in pairing mode, read its key characteristic over an
 * encrypted link (reading it makes Android bond), store id + key, and adopt its counter.
 */
@Suppress("MissingPermission")
class Pairer(private val ctx: Context, private val status: (msg: String, done: Boolean) -> Unit) {
    private val main = Handler(Looper.getMainLooper())
    private val adapter = ctx.getSystemService(BluetoothManager::class.java).adapter
    private var gatt: BluetoothGatt? = null
    private var scanning: ScanCallback? = null
    private var readAttempts = 0
    private var finished = false

    fun start() {
        status("Looking for tune-button in pairing mode (hold both buttons 3 s, or one button 5 s)…", false)
        val cb = object : ScanCallback() {
            override fun onScanResult(type: Int, result: ScanResult) {
                stopScan()
                connect(result.device)
            }
            override fun onScanFailed(errorCode: Int) = finish("Scan failed ($errorCode)", false)
        }
        scanning = cb
        adapter.bluetoothLeScanner.startScan(
            listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(SERVICE)).build()),
            ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), cb,
        )
        main.postDelayed({ if (!finished && gatt == null) finish("Not found. Is it in pairing mode?", false) }, 30_000)
    }

    fun cancel() = finish("Cancelled", false)

    private fun stopScan() {
        scanning?.let { try { adapter.bluetoothLeScanner?.stopScan(it) } catch (e: Exception) { } }
        scanning = null
    }

    private fun connect(device: BluetoothDevice) {
        status("Connecting…", false)
        gatt = device.connectGatt(ctx, false, object : BluetoothGattCallback() {
            override fun onConnectionStateChange(g: BluetoothGatt, st: Int, newState: Int) {
                if (newState == BluetoothProfile.STATE_CONNECTED) main.post { g.discoverServices() }
                else if (newState == BluetoothProfile.STATE_DISCONNECTED) main.post { finish("Disconnected before the key was read", false) }
            }

            override fun onServicesDiscovered(g: BluetoothGatt, st: Int) = main.post { read(g) }.let { }

            @Deprecated("Pre-33 callback")
            override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, st: Int) {
                @Suppress("DEPRECATION") handleRead(g, c.value, st)
            }

            override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray, st: Int) =
                handleRead(g, value, st)
        }, BluetoothDevice.TRANSPORT_LE)
    }

    private fun read(g: BluetoothGatt) {
        val c = g.getService(SERVICE)?.getCharacteristic(KEY) ?: return finish("Not a tune-button", false)
        status("Pairing… accept the Bluetooth pairing request if one appears", false)
        g.readCharacteristic(c)
    }

    private fun handleRead(g: BluetoothGatt, value: ByteArray?, st: Int) = main.post {
        if (st == BluetoothGatt.GATT_SUCCESS && value != null && value.size == 24) {
            val store = Store(ctx)
            store.device = Store.Device(value.copyOfRange(0, 4), value.copyOfRange(4, 20))
            val counter = (0 until 4).fold(0L) { acc, i -> acc or ((value[20 + i].toLong() and 0xFF) shl (8 * i)) }
            store.resetCounter(counter)
            value.fill(0)
            val problem = Scanner.register(ctx)
            finish(if (problem == null) "Paired. Presses will be heard in the background." else "Paired, but: $problem", true)
        } else if (++readAttempts < 6) {
            // Insufficient authentication: Android is bonding; read again once it has.
            main.postDelayed({ if (!finished) read(g) }, 2500)
        } else {
            finish("Could not read the key (status $st)", false)
        }
    }.let { }

    private fun finish(msg: String, ok: Boolean) {
        if (finished) return
        finished = true
        stopScan()
        gatt?.let { it.disconnect(); it.close() }
        gatt = null
        status(if (ok) "✓ $msg" else msg, true)
    }

    companion object {
        val SERVICE: UUID = UUID.fromString("7b1e0001-5f3a-4c1e-9b7a-2e6c0d1a7b00")
        val KEY: UUID = UUID.fromString("7b1e0002-5f3a-4c1e-9b7a-2e6c0d1a7b00")
    }
}
