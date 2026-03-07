"""配置模块测试"""

import os
import tempfile
import yaml
from pathlib import Path
import pytest
from config import Settings, ModelConfig, ToolConfig


class TestConfig:
    """配置测试类"""

    def test_model_config_defaults(self):
        """测试模型配置默认值"""
        config = ModelConfig()
        assert config.name == "deepseek-chat"
        assert config.temperature == 0.1
        assert config.max_tokens == 8000
        assert config.gateway == "openai"
        assert config.multimodal is False

    def test_model_config_env_vars(self, monkeypatch):
        """测试模型配置环境变量"""
        monkeypatch.setenv("LLM_API_KEY", "test_key")
        monkeypatch.setenv("LLM_API_URL", "https://test.com/v1")
        monkeypatch.setenv("LLM_MODEL_NAME", "test-model")
        monkeypatch.setenv("LLM_GATEWAY", "anthropic")

        config = ModelConfig()
        assert config.api_key == "test_key"
        assert config.base_url == "https://test.com/v1"
        assert config.name == "test-model"
        assert config.gateway == "anthropic"

    def test_tools_config_defaults(self):
        """测试工具配置默认值"""
        config = ToolConfig()
        assert config.enable_code_execution is True
        assert config.enable_file_ops is True
        assert config.enable_sandbox is False
        assert config.enable_search is True
        assert config.enable_shell is True
        assert config.enable_testing is True
        assert config.enable_web_search is True
        assert config.max_execution_time == 60
        assert config.sandbox_type == "docker"

    def test_settings_load_from_yaml(self):
        """测试从YAML文件加载配置"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_data = {
                "model": {"name": "test-model", "temperature": 0.5, "max_tokens": 4000},
                "tools": {"enable_code_execution": False, "max_execution_time": 30},
            }
            yaml.dump(yaml_data, f)
            config_file = f.name

        try:
            settings = Settings(config_file=config_file)
            assert settings.model.name == "test-model"
            assert settings.model.temperature == 0.5
            assert settings.model.max_tokens == 4000
            assert settings.tools.enable_code_execution is False
            assert settings.tools.max_execution_time == 30
        finally:
            os.unlink(config_file)

    def test_settings_env_priority(self, monkeypatch):
        """测试环境变量优先级高于配置文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_data = {"model": {"name": "file-model", "api_key": "file-key"}}
            yaml.dump(yaml_data, f)
            config_file = f.name

        try:
            monkeypatch.setenv("LLM_MODEL_NAME", "env-model")
            monkeypatch.setenv("LLM_API_KEY", "env-key")

            settings = Settings(config_file=config_file)
            # 环境变量应该优先
            assert settings.model.name == "env-model"
            assert settings.model.api_key == "env-key"
        finally:
            os.unlink(config_file)

    def test_config_validation(self):
        """测试配置验证"""
        settings = Settings()

        # 默认情况下应该没有API密钥
        errors = settings.validate()
        assert len(errors) > 0
        assert "未配置LLM API密钥" in errors[0]

    def test_config_validation_with_env(self, monkeypatch):
        """测试带环境变量的配置验证"""
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        # 创建临时配置文件禁用多模态和web搜索
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_data = {
                "multimodal": {"enabled": False},
                "tools": {"enable_web_search": False},
            }
            yaml.dump(yaml_data, f)
            config_file = f.name

        try:
            settings = Settings(config_file=config_file)
            errors = settings.validate()

            # 有API密钥且多模态禁用时应该没有错误
            assert len(errors) == 0
        finally:
            os.unlink(config_file)

    def test_get_validated_config(self, monkeypatch):
        """测试获取验证后的配置"""
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        # 创建临时配置文件禁用多模态和web搜索
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_data = {
                "multimodal": {"enabled": False},
                "tools": {"enable_web_search": False},
            }
            yaml.dump(yaml_data, f)
            config_file = f.name

        try:
            settings = Settings(config_file=config_file)
            config = settings.get_validated_config()

            assert "model" in config
            assert "tools" in config
            assert "safety" in config
            assert "context" in config
            assert isinstance(config["model"], dict)
            assert isinstance(config["tools"], dict)
        finally:
            os.unlink(config_file)

    def test_get_validated_config_failure(self):
        """测试配置验证失败"""
        settings = Settings()

        with pytest.raises(ValueError) as exc_info:
            settings.get_validated_config()

        assert "配置验证失败" in str(exc_info.value)
        assert "未配置LLM API密钥" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
