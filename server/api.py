# API module for desktop client configuration management
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml


class ConfigAPI:
    """Configuration API for desktop client"""

    def __init__(self):
        self.config_path = Path.home() / ".aacode" / "aacode_config.yaml"
        self.recent_projects_path = Path.home() / ".aacode" / "recent_projects.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    if config:
                        return config
            except Exception:
                pass

        return {
            "model": {
                "name": "deepseek-chat",
                "api_key": "",
                "base_url": "",
                "temperature": 0.1,
                "max_tokens": 8000,
                "gateway": "openai",
                "multimodal": False,
            }
        }

    def save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            return True
        except Exception:
            return False

    def update_model_config(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        gateway: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update model configuration"""
        config = self.get_config()

        if "model" not in config:
            config["model"] = {}

        if api_key is not None:
            config["model"]["api_key"] = api_key
            os.environ["LLM_API_KEY"] = api_key

        if model is not None:
            config["model"]["name"] = model
            os.environ["LLM_MODEL_NAME"] = model

        if base_url is not None:
            config["model"]["base_url"] = base_url
            os.environ["LLM_API_URL"] = base_url

        if temperature is not None:
            config["model"]["temperature"] = temperature

        if gateway is not None:
            config["model"]["gateway"] = gateway
            os.environ["LLM_GATEWAY"] = gateway

        self.save_config(config)
        return config

    def get_recent_projects(self) -> List[Dict[str, str]]:
        """Get recent opened projects"""
        if self.recent_projects_path.exists():
            try:
                with open(self.recent_projects_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def add_recent_project(self, path: str, name: str) -> bool:
        """Add a project to recent list"""
        try:
            projects = self.get_recent_projects()

            projects = [p for p in projects if p.get("path") != path]

            projects.insert(0, {"path": path, "name": name})

            projects = projects[:10]

            with open(self.recent_projects_path, "w", encoding="utf-8") as f:
                json.dump(projects, f, ensure_ascii=False, indent=2)

            return True
        except Exception:
            return False

    def validate_api_key(
        self, api_key: str, model: str = "deepseek-chat", base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate API key by making a simple test request"""
        import asyncio
        from .runner import AICoderRunner

        async def _validate():
            runner = AICoderRunner(project_path=str(Path.home() / ".aacode"))
            try:
                result = await runner.validate_api_key(api_key, model, base_url)
                return result
            finally:
                await runner.cleanup()

        try:
            return asyncio.run(_validate())
        except Exception as e:
            return {"valid": False, "error": str(e)}
