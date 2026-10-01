"""阿里云号码认证的服务端调用；SDK 密钥仅用于 iOS，AccessKey 仅用于这里。"""
import json

from alibabacloud_dypnsapi20170525.client import Client
from alibabacloud_dypnsapi20170525 import models
from alibabacloud_tea_openapi import models as openapi_models

from ..config import settings


class PhoneServiceUnavailable(Exception):
    pass


def _client():
    if not settings.aliyun_access_key_id or not settings.aliyun_access_key_secret:
        raise PhoneServiceUnavailable("号码认证服务未配置")
    return Client(openapi_models.Config(
        access_key_id=settings.aliyun_access_key_id,
        access_key_secret=settings.aliyun_access_key_secret,
        endpoint="dypnsapi.aliyuncs.com",
    ))


def send_sms(phone: str) -> None:
    try:
        body = _client().send_sms_verify_code(models.SendSmsVerifyCodeRequest(
            phone_number=phone,
            sign_name=settings.aliyun_sms_sign_name,
            template_code=settings.aliyun_sms_template_code,
            template_param=json.dumps({"code": "##code##", "min": "5"}),
            scheme_name=settings.aliyun_sms_scheme_name,
            code_type=1, code_length=6, valid_time=300, interval=60,
            return_verify_code=False,
        )).body
        if body.code != "OK" or body.success is not True:
            raise PhoneServiceUnavailable("验证码发送失败，请稍后重试")
    except PhoneServiceUnavailable:
        raise
    except Exception as exc:
        raise PhoneServiceUnavailable("验证码发送失败，请稍后重试") from exc


def check_sms(phone: str, code: str) -> bool:
    try:
        body = _client().check_sms_verify_code(models.CheckSmsVerifyCodeRequest(
            phone_number=phone, verify_code=code,
            scheme_name=settings.aliyun_sms_scheme_name,
        )).body
        if body.code != "OK" or body.success is not True:
            raise PhoneServiceUnavailable("验证码核验服务暂不可用")
        return body.model is not None and body.model.verify_result == "PASS"
    except PhoneServiceUnavailable:
        raise
    except Exception as exc:
        raise PhoneServiceUnavailable("验证码核验服务暂不可用") from exc


def get_mobile(access_token: str) -> str:
    try:
        body = _client().get_mobile(models.GetMobileRequest(access_token=access_token)).body
        mobile = body.get_mobile_result_dto.mobile if body.get_mobile_result_dto else ""
        if body.code == "OK" and len(mobile) == 11 and mobile.startswith("1") and mobile.isdigit():
            return mobile
        raise PhoneServiceUnavailable("本机号码验证失败，请改用短信验证码")
    except PhoneServiceUnavailable:
        raise
    except Exception as exc:
        raise PhoneServiceUnavailable("本机号码验证失败，请改用短信验证码") from exc
