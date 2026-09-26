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

    # 监护人核验：mock（开发）| aliyun | tencent
    guardian_verify_provider: str = "mock"

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()
