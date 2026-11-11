package com.omniaide.omniaide_mobile

import android.content.ClipboardManager
import android.content.Context
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterFragmentActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "omniaide/clipboard"
        ).setMethodCallHandler { call, result ->
            if (call.method != "readImage") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            try {
                val manager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                val clip = manager.primaryClip
                if (clip == null || clip.itemCount == 0) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                val uri = clip.getItemAt(0).uri
                if (uri == null) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                val mime = contentResolver.getType(uri) ?: "image/png"
                if (!mime.startsWith("image/")) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
                if (bytes == null || bytes.isEmpty()) {
                    result.success(null)
                    return@setMethodCallHandler
                }
                result.success(
                    mapOf(
                        "bytes" to bytes,
                        "mime" to mime,
                        "name" to "clipboard"
                    )
                )
            } catch (e: Exception) {
                result.error("clipboard_failed", e.message, null)
            }
        }
    }
}
