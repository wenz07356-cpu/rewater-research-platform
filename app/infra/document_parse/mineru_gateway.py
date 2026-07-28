# dataclass版本
from dataclasses import dataclass
from app.infra.config.providers import infra_config

@dataclass(frozen=True)
#dataclass可以不用写__init__、__repr__、这些代码
# frozen=True 代表只读，更安全！
class MinerUGateway:
    # 直接声明属性 + 默认值从配置读取
    base_url: str = infra_config.mineru.base_url
    api_key: str = infra_config.mineru.api_key

mineru_gateway = MinerUGateway()