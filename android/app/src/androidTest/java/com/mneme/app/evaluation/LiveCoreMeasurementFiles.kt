package com.mneme.app.evaluation

import android.content.Context
import android.graphics.Bitmap
import android.os.Build
import androidx.test.core.app.ApplicationProvider
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.util.Locale

internal object LiveCoreMeasurementFiles {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val prettyJson = Json { prettyPrint = true }
    private val outputDirectory =
        File(
            requireNotNull(context.getExternalFilesDir(null)) {
                "App-specific external storage is required for live-core artifacts."
            },
            "live-core-evaluation",
        )

    fun resetCsv(
        fileName: String,
        header: List<String>,
    ) {
        outputDirectory.deleteRecursively()
        outputDirectory.mkdirs()
        file(fileName).writeText(header.joinToString(",") + "\n")
        writeEnvironment()
    }

    @Synchronized
    fun appendCsv(
        fileName: String,
        values: List<Any?>,
    ) {
        file(fileName).appendText(values.joinToString(",") { value -> csv(value) } + "\n")
    }

    fun captureScreenshot(fileName: String) {
        val screenshot =
            requireNotNull(
                InstrumentationRegistry
                    .getInstrumentation()
                    .uiAutomation
                    .takeScreenshot(),
            ) {
                "Android did not return a screenshot."
            }
        file(fileName).outputStream().use { output ->
            check(screenshot.compress(Bitmap.CompressFormat.PNG, 100, output)) {
                "Android could not encode $fileName."
            }
        }
        screenshot.recycle()
    }

    private fun writeEnvironment() {
        val runtime = Runtime.getRuntime()
        val displayMetrics = context.resources.displayMetrics
        val payload =
            buildJsonObject {
                put("schema_version", "live-core-android-environment-v1")
                put("device_manufacturer", Build.MANUFACTURER)
                put("device_model", Build.MODEL)
                put("device_product", Build.PRODUCT)
                put("android_sdk", Build.VERSION.SDK_INT)
                put("android_release", Build.VERSION.RELEASE)
                put("build_fingerprint", Build.FINGERPRINT)
                put("available_processors", runtime.availableProcessors())
                put("max_heap_bytes", runtime.maxMemory())
                put("screen_width_pixels", displayMetrics.widthPixels)
                put("screen_height_pixels", displayMetrics.heightPixels)
                put("screen_density_dpi", displayMetrics.densityDpi)
                put(
                    "is_emulator",
                    Build.FINGERPRINT.contains("generic") ||
                        Build.MODEL.contains("sdk_gphone") ||
                        Build.PRODUCT.contains("sdk_gphone"),
                )
            }
        file("environment.json").writeText(
            prettyJson.encodeToString(payload) + "\n",
        )
    }

    private fun file(fileName: String): File = File(outputDirectory, fileName)

    private fun csv(value: Any?): String {
        val text =
            when (value) {
                null -> ""
                is Double -> String.format(Locale.US, "%.3f", value)
                else -> value.toString()
            }
        return if (text.any { character -> character == ',' || character == '"' || character == '\n' }) {
            "\"${text.replace("\"", "\"\"")}\""
        } else {
            text
        }
    }
}
