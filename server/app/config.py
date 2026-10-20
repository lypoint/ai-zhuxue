"""集中配置：全部来自环境变量，生产通过 docker-compose/.env 注入。"""
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 基础
    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite:///./aizhuxue.db"
    jwt_secret: str = "change-me-in-prod"
    jwt_expire_hours: int = 24 * 7
    llm_key_secret: str = ""  # LLM api_key 落库加密密钥；空则回落 jwt_secret
    cors_origins: str = ""  # 生产后台页面的完整 Origin，多个用逗号分隔
    upload_dir: str = "./uploads"  # CMS 老师头像
    image_features_enabled: bool = False  # 紧急关闭后不接收上传、不执行配图；历史已审核图片仍可查看
    qiniu_access_key: str = ""
    qiniu_secret_key: str = ""
    qiniu_bucket: str = ""
    qiniu_domain: str = ""  # 私有空间 HTTPS 下载域名
    qiniu_upload_url: str = "https://upload.qiniup.com"  # 按 Bucket 地域设置
    qiniu_censor_url: str = "https://ai.qiniuapi.com/v3/image/censor"
    image_max_bytes: int = 8 * 1024 * 1024
    image_max_pixels: int = 20_000_000
    image_font_path: str = ""  # 绘图中文标签所需的部署字体路径

    # LLM 提供商：glm | deepseek | kimi（均 OpenAI 兼容协议）
    llm_provider: str = "glm"
    glm_api_key: str = ""
    deepseek_api_key: str = ""
    kimi_api_key: str = ""
    openrouter_api_key: str = ""
    chat_model: str = ""                  # 留空则用各 provider 默认
    fence_model: str = ""                 # 围栏分类用低成本档，默认同 chat_model

    # 围栏：llm = 分类模型+白名单+二次判定；heuristic = 仅规则（无 API Key 时的降级模式）
    fence_mode: str = "heuristic"
    # 本地时区偏移（小时）：created_at 统一存 UTC，本地日界/时段禁用按此换算；中国=8
    tz_offset_hours: int = 8
    # 安全优先流式：true=LLM 完成后先全文复核、通过再回放（首字延迟数秒，未成年人产品推荐）
    # false=实时流出 + 尾部复核（已送达部分无法撤回）
    stream_recheck_first: bool = True
    fence_daily_message_cap: int = 200    # 每学生每日消息上限（时长管控的服务端部分）
    fence_quiet_enabled: bool = True
    fence_quiet_start: int = 22           # 22:00-6:00 禁用（未成年人模式建设指南）
    fence_quiet_end: int = 6

    # 订阅策略：仅用于首次初始化数据库配置，运行中的业务始终读库。
    pricing_base_monthly_price: float = 66.0
    pricing_additional_seat_price: float = 33.0
    pricing_trial_days: int = 30
    pricing_post_trial_daily_free_count: int = 0

    # Demo never calls WeChat and is forbidden in production.
    payment_mode: Literal["demo", "wechat"] = "demo"
    wechat_app_id: str = "wx_demo_parent_app"
    wechat_mch_id: str = "demo_merchant"
    wechat_merchant_serial: str = "DEMO_MERCHANT_SERIAL"
    wechat_private_key_path: str = ""
    wechat_api_v3_key: str = "demo_only_0123456789012345678901"
    wechat_platform_serial: str = "DEMO_PLATFORM_SERIAL"
    wechat_platform_public_key_path: str = ""
    wechat_notify_url: str = "https://demo.example.com/payments/wechat/notify"

    # JSON: {"appstore":{"family_monthly_1":"store.product.id"},"googleplay":{...}}
    store_products_json: str = "{}"
    store_token_secret: str = ""  # Fernet key (generate once, retain across deployments)
    store_test_account_tokens: str = ""  # comma-separated family UUIDs allowed for review/test purchases
    apple_environment: Literal["Production", "Sandbox"] = "Production"
    apple_bundle_id: str = "com.aizhuxue.appParent"
    apple_app_id: int = 0
    apple_issuer_id: str = ""
    apple_key_id: str = ""
    apple_private_key_path: str = ""
    apple_root_cert_paths: str = ""  # comma-separated Apple root DER certificates
    google_login_client_id: str = ""  # OAuth Web client ID accepted as Google login audience.
    google_package_name: str = "com.aizhuxue.parent.play"
    google_service_account_path: str = ""
    google_gateway_url: str = ""  # Optional HTTPS origin for the dedicated Google relay.
    google_gateway_token: str = ""
    google_pubsub_audience: str = ""
    google_pubsub_email: str = ""

    # 阿里云号码认证：仅服务端保存 AccessKey；客户端只持有 iOS 方案的 SDK 密钥。
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    aliyun_sms_sign_name: str = "AI助学演示"
    aliyun_sms_template_code: str = "100001"
    aliyun_sms_scheme_name: str = "AI助学家长登录"

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()
