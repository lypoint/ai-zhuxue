"""监护人三要素核验（姓名+身份证号+手机号，权威数据源一致性比对，不采集人脸）。

生产接入：阿里云「信息核验」/腾讯云 PhoneVerification（企业实名认证即可开通，S53）。
核验强度边界（三要素≠本人操作）由法务意见问题2界定；可叠加监护人实名支付绑定增强。
"""
import re

from ..config import settings

_ID_RE = re.compile(r"^\d{15}$|^\d{17}[\dXx]$")
_PHONE_RE = re.compile(r"^1\d{10}$")


class VerifyResult:
    def __init__(self, passed: bool, provider: str, detail: str = ""):
        self.passed = passed
        self.provider = provider
        self.detail = detail


async def verify(real_name: str, id_number: str, phone: str) -> VerifyResult:
    provider = settings.guardian_verify_provider
    if not _ID_RE.match(id_number) or not _PHONE_RE.match(phone) or len(real_name) < 2:
        return VerifyResult(False, provider, "format invalid")
    if provider == "mock":
        # 开发模式：格式合法即通过。生产切换 aliyun/tencent 并配置密钥。
        return VerifyResult(True, provider, "mock always pass")
    # TODO(生产): 调用云厂商三要素 API，按返回码判定一致性；失败时计费与否见厂商说明
    raise NotImplementedError(f"provider {provider} not wired yet")
