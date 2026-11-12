package com.aizhuxue.app_parent

import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "ai.zhuxue/device_info")
            .setMethodCallHandler { call, result ->
                if (call.method == "registrationDevice") {
                    result.success(mapOf("brand" to Build.BRAND, "model" to Build.MODEL))
                } else result.notImplemented()
            }
    }
}
