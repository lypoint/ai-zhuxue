import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';

String registrationOsVersion() => Platform.operatingSystemVersion;

Future<Map<String, String>> registrationHardware() async {
  if (defaultTargetPlatform != TargetPlatform.android &&
      defaultTargetPlatform != TargetPlatform.iOS) {
    return {};
  }
  try {
    return await const MethodChannel(
          'ai.zhuxue/device_info',
        ).invokeMapMethod<String, String>('registrationDevice') ??
        {};
  } on MissingPluginException {
    return {};
  } on PlatformException {
    return {};
  }
}
