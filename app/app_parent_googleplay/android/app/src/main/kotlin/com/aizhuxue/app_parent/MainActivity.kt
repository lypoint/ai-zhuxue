package com.aizhuxue.app_parent

import com.mobile.auth.gatewayauth.PhoneNumberAuthHelper
import com.mobile.auth.gatewayauth.ResultCode
import com.mobile.auth.gatewayauth.TokenResultListener
import com.mobile.auth.gatewayauth.model.TokenRet
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var helper: PhoneNumberAuthHelper? = null
    private var pending: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "ai.zhuxue/one_tap")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "isAvailable" -> {
                        val key = call.argument<String>("sdkKey") ?: ""
                        if (key.isEmpty()) { result.success(false); return@setMethodCallHandler }
                        try {
                            helper = PhoneNumberAuthHelper.getInstance(this, listener)
                            helper?.setAuthSDKInfo(key)
                            result.success(helper?.checkEnvAvailable() == true)
                        } catch (_: Exception) {
                            result.success(false)
                        }
                    }
                    "getLoginToken" -> {
                        val auth = helper
                        if (auth == null || pending != null) {
                            result.error("ONE_TAP_UNAVAILABLE", "请使用短信验证码登录", null)
                        } else {
                            pending = result
                            auth.getLoginToken(this, 8000)
                            Handler(Looper.getMainLooper()).postDelayed({
                                if (pending === result) finishLogin(null)
                            }, 15000)
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private val listener = object : TokenResultListener {
        override fun onTokenSuccess(raw: String) {
            val response = try { TokenRet.fromJson(raw) } catch (_: Exception) { null }
            if (response == null) finishLogin(null)
            else if (response.code == ResultCode.CODE_SUCCESS) finishLogin(response.token)
        }

        override fun onTokenFailed(raw: String) {
            finishLogin(null)
        }
    }

    private fun finishLogin(token: String?) {
        runOnUiThread {
            val result = pending ?: return@runOnUiThread
            pending = null
            helper?.quitLoginPage()
            if (token.isNullOrEmpty()) result.error("ONE_TAP_UNAVAILABLE", "请使用短信验证码登录", null)
            else result.success(token)
        }
    }
}
