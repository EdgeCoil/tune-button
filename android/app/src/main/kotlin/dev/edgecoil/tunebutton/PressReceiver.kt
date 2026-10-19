// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
package dev.edgecoil.tunebutton

import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanResult
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import androidx.work.workDataOf
import org.json.JSONObject

/** Receives scan results from the system, verifies them, and hands each new press to PressWorker. */
class PressReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val store = Store(ctx)
        val error = intent.getIntExtra(BluetoothLeScanner.EXTRA_ERROR_CODE, 0)
        if (error != 0) {
            store.log(JSONObject().put("kind", "scan-error").put("code", error))
            return
        }
        val device = store.device ?: return
        @Suppress("DEPRECATION")
        val results: List<ScanResult> = (if (Build.VERSION.SDK_INT >= 33)
            intent.getParcelableArrayListExtra(BluetoothLeScanner.EXTRA_LIST_SCAN_RESULT, ScanResult::class.java)
        else intent.getParcelableArrayListExtra(BluetoothLeScanner.EXTRA_LIST_SCAN_RESULT)) ?: return

        for (r in results) {
            val data = r.scanRecord?.getManufacturerSpecificData(Packet.COMPANY_ID)
            val press = Packet.verify(data, device.id, device.key) ?: continue
            if (!store.advanceCounter(press.counter)) continue  // a repeat from the same burst, or a replay
            val work = OneTimeWorkRequestBuilder<PressWorker>()
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .setInputData(workDataOf(
                    "button" to press.button, "counter" to press.counter, "battery" to (press.battery ?: -1),
                    "age_ms" to press.ageMs, "rssi" to r.rssi,
                ))
                .build()
            WorkManager.getInstance(ctx).enqueue(work)
        }
    }
}
