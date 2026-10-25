// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.UUID

/**
 * Pairing and key settings (protocol/spec.md). Both start with the button in pairing mode.
 *
 * Pairing reads the key characteristic over an encrypted link (reading it makes Android bond),
 * stores id + key, adopts the counter, then sends the key settings. Sending settings alone writes
 * the settings characteristic, tagged with the paired key, and reads it back; no new bond or key.
 */
@Suppress("MissingPermission")
class Pairer(
    private val ctx: Context,
    private val pair: Boolean,
    private val status: (msg: String, done: Boolean) -> Unit,
) {
    private val main = Handler(Looper.getMainLooper())
    private val adapter = ctx.getSystemService(BluetoothManager::class.java).adapter
    private val store = Store(ctx)
    private var gatt: BluetoothGatt? = null
    private var scanning: ScanCallback? = null
    private var readAttempts = 0
    private var finished = false
    private var sent = -1
    private var refreshed = false
    private var keyRead = false

    fun start() {
        status("Looking for tune-button in pairing mode (hold keys 1 and 2 for 3 s, or a one-button build's key for 5 s)…", false)
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
                else if (newState == BluetoothProfile.STATE_DISCONNECTED) main.post { finish("Disconnected too soon; try again", false) }
            }

            override fun onServicesDiscovered(g: BluetoothGatt, st: Int) =
                main.post { if (pair && !keyRead) readKey(g) else readSettings(g) }.let { }

            @Deprecated("Pre-33 callback")
            override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, st: Int) {
                @Suppress("DEPRECATION") handleRead(g, c.uuid, c.value, st)
            }

            override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray, st: Int) =
                handleRead(g, c.uuid, value, st)

            override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, st: Int) = main.post {
                if (st == BluetoothGatt.GATT_SUCCESS) readSettings(g) else finish("The button didn't take the settings (status $st)", false)
            }.let { }
        }, BluetoothDevice.TRANSPORT_LE)
    }

    private fun readKey(g: BluetoothGatt) {
        val c = g.getService(SERVICE)?.getCharacteristic(KEY) ?: return finish("Not a tune-button", false)
        status("Pairing… accept the Bluetooth pairing request if one appears", false)
        g.readCharacteristic(c)
    }

    private fun readSettings(g: BluetoothGatt) {
        val c = g.getService(SERVICE)?.getCharacteristic(SETTINGS)
        if (c == null && !refreshed) {
            // A phone bonded before the firmware update may hold a cached copy of the old service
            // table, which has no settings characteristic. Drop the cache (a hidden API) and look again.
            refreshed = true
            val ok = try { g.javaClass.getMethod("refresh").invoke(g) as Boolean } catch (e: Exception) { false }
            if (ok) { main.postDelayed({ if (!finished) g.discoverServices() }, 600); return }
        }
        if (c == null) {
            return if (pair) finish(paired("this button's firmware has no hold or double press: update it to use them"), true)
            else finish("This button's firmware has no key settings; update it first", false)
        }
        g.readCharacteristic(c)
    }

    private fun handleRead(g: BluetoothGatt, uuid: UUID, value: ByteArray?, st: Int) = main.post {
        if (uuid == SETTINGS) return@post handleSettings(g, value, st)
        if (st == BluetoothGatt.GATT_SUCCESS && value != null && value.size == 24) {
            store.device = Store.Device(value.copyOfRange(0, 4), value.copyOfRange(4, 20))
            val counter = (0 until 4).fold(0L) { acc, i -> acc or ((value[20 + i].toLong() and 0xFF) shl (8 * i)) }
            store.resetCounter(counter)
            store.deviceSettings = -1
            keyRead = true
            value.fill(0)
            status("Paired. Sending key settings…", false)
            readSettings(g)
        } else if (++readAttempts < 6) {
            // Insufficient authentication: Android is bonding; read again once it has.
            main.postDelayed({ if (!finished) readKey(g) }, 2500)
        } else {
            finish("Could not read the key (status $st)", false)
        }
    }.let { }

    /** Settings reads as nonce (8) | current settings (1). The first read gets a nonce; the read after a write checks it took. */
    private fun handleSettings(g: BluetoothGatt, value: ByteArray?, st: Int) {
        if (st != BluetoothGatt.GATT_SUCCESS || value == null || value.size != 9) return finish("Could not read the settings (status $st)", false)
        if (sent >= 0) {
            if ((value[8].toInt() and 0xFF) != sent) return finish("The button didn't take the settings; was it paired with another phone?", false)
            store.deviceSettings = sent
            return finish(if (pair) paired(null) else "Key settings sent", true)
        }
        val device = store.device ?: return finish("Not paired", false)
        val want = store.wantedSettings
        val c = g.getService(SERVICE).getCharacteristic(SETTINGS)
        val bytes = byteArrayOf(want.toByte()) + Packet.settingsTag(device.key, value.copyOfRange(0, 8), want)
        sent = want
        val ok = if (Build.VERSION.SDK_INT >= 33)
            g.writeCharacteristic(c, bytes, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothStatusCodes.SUCCESS
        else {
            @Suppress("DEPRECATION")
            c.value = bytes
            @Suppress("DEPRECATION")
            g.writeCharacteristic(c)
        }
        if (!ok) finish("Could not send the settings", false)
    }

    private fun paired(note: String?): String {
        val problem = Scanner.register(ctx)
        return listOfNotNull("Paired. Presses will be heard in the background.", note, problem?.let { "But: $it" })
            .joinToString(" ")
    }

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
        val SETTINGS: UUID = UUID.fromString("7b1e0003-5f3a-4c1e-9b7a-2e6c0d1a7b00")
    }
}
