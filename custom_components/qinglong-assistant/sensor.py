"""Sensor platform for QingLong integration."""

from __future__ import annotations
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TOKEN_REFRESH_THRESHOLD, TOKEN_EXPIRY_BUFFER

_LOGGER = logging.getLogger(__name__)

# 轮询间隔 - 30秒
SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up QingLong sensors from a config entry."""
    
    data = hass.data[DOMAIN][entry.entry_id]
    client = data.get("client")
    host = data.get("host")
    port = data.get("port")
    tasks_data = data.get("tasks", {})
    
    # Create sensor entities
    sensors = [
        QingLongTokenSensor(entry, client, host, port),
        QingLongTasksSensor(entry, tasks_data, host, port),
    ]
    
    async_add_entities(sensors, True)


class QingLongTokenSensor(SensorEntity):
    """Representation of a QingLong token sensor."""
    
    # 设置轮询间隔
    _attr_should_poll = True
    
    def __init__(self, entry: ConfigEntry, client, host: str, port: int):
        """Initialize the sensor."""
        self._entry = entry
        self._client = client
        self._host = host
        self._port = port
        self._last_update = 0
        
        # Entity properties
        self._attr_name = "Token"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_token"
        self._attr_icon = "mdi:lock"
        
        # 初始状态
        self._update_state()
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"青龙面板 ({host}:{port})",
            "manufacturer": "青龙面板",
            "model": "QingLong",
        }
    
    def _update_state(self):
        """Update sensor state from client."""
        if self._client:
            token_info = self._client.get_token_info()
            current_time = int(time.time())
            
            # 设置主值：显示完整的token字符串
            # 从client获取完整token（而不是token_info中的部分token）
            self._attr_native_value = self._client._token
            
            # 设置额外属性
            self._attr_extra_state_attributes = {
                "host": self._host,
                "port": self._port,
                # 注意：这里不再包含token_preview属性
                "token_expires_at": token_info["expires_at"],
                "token_expires_in_seconds": token_info["expires_in"],
                "token_expires_display": token_info["expires_display"],
                "is_valid": token_info["is_valid"],
                "needs_refresh": token_info["needs_refresh"],
                "last_refresh_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(token_info["last_refresh_time"])) if token_info["last_refresh_time"] > 0 else "从未刷新",
                "last_updated": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time)),
                "polling_interval": "30秒",
            }
        else:
            self._attr_native_value = "客户端未初始化"
            self._attr_extra_state_attributes = {
                "host": self._host,
                "port": self._port,
                "connection_status": "disconnected",
                "polling_interval": "30秒",
            }
    
    @property
    def native_value(self) -> str:
        """Return sensor value."""
        return self._attr_native_value
    
    async def async_update(self) -> None:
        """Update sensor state."""
        current_time = time.time()
        
        # 检查是否需要更新（避免过于频繁的API调用）
        if current_time - self._last_update < 30:
            return
            
        # 触发客户端检查token是否需要刷新
        if self._client:
            await self._client._refresh_token_if_needed()
            self._last_update = current_time
            self._update_state()
            _LOGGER.debug("Token sensor updated")


class QingLongTasksSensor(SensorEntity):
    """Representation of a QingLong tasks sensor."""
    
    # 设置轮询间隔
    _attr_should_poll = True
    
    def __init__(self, entry: ConfigEntry, tasks_data: Any, host: str, port: int):
        """Initialize the sensor."""
        self._entry = entry
        self._tasks_data = tasks_data
        self._host = host
        self._port = port
        self._last_update = 0
        
        # Entity properties
        self._attr_name = "定时任务"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_tasks"
        self._attr_icon = "mdi:calendar-clock"
        
        # Extract tasks list
        tasks_list = self._extract_tasks_list(tasks_data)
        
        # Sensor properties
        self._attr_native_value = len(tasks_list)
        self._attr_extra_state_attributes = self._get_tasks_attributes(tasks_list)
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"青龙面板 ({host}:{port})",
            "manufacturer": "青龙面板",
            "model": "QingLong",
        }
    
    def _extract_tasks_list(self, tasks_data: Any) -> list:
        """Extract tasks list from tasks data."""
        if isinstance(tasks_data, dict) and "data" in tasks_data:
            inner_data = tasks_data["data"]
            if isinstance(inner_data, dict) and "data" in inner_data:
                # Structure: {"data": {"data": [...], "total": 2}}
                return inner_data.get("data", [])
            elif isinstance(inner_data, list):
                # Direct list
                return inner_data
        
        return []
    
    def _get_tasks_attributes(self, tasks_list: list) -> dict:
        """Get tasks list attributes."""
        attributes = {
            "total_tasks": len(tasks_list),
            "commands": [],  # 将原来的"task_names"改为"commands"
            "enabled_tasks": 0,
            "disabled_tasks": 0,
            "last_updated": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            "polling_interval": "30秒",
        }
        
        for task in tasks_list:
            if isinstance(task, dict):
                # 添加command属性
                command = task.get("command", "")
                attributes["commands"].append(command)
                
                # 统计启用/禁用的任务
                if task.get("isDisabled"):
                    attributes["disabled_tasks"] += 1
                else:
                    attributes["enabled_tasks"] += 1
        
        return attributes
    
    @property
    def native_value(self) -> int:
        """Return number of tasks."""
        tasks_list = self._extract_tasks_list(self._tasks_data)
        return len(tasks_list)
    
    @property
    def native_unit_of_measurement(self) -> str:
        """Return unit."""
        return "个"
    
    async def async_update(self) -> None:
        """Update tasks list."""
        current_time = time.time()
        
        # 检查是否需要更新（避免过于频繁的API调用）
        if current_time - self._last_update < 30:
            return
            
        try:
            data = self.hass.data[DOMAIN][self._entry.entry_id]
            client = data.get("client")
            
            if client:
                # Get latest tasks data
                new_tasks_data = await client.async_get_tasks()
                self._last_update = current_time
                self._tasks_data = new_tasks_data
                
                # Update sensor value
                tasks_list = self._extract_tasks_list(new_tasks_data)
                self._attr_native_value = len(tasks_list)
                self._attr_extra_state_attributes = self._get_tasks_attributes(tasks_list)
                
                # Update stored data
                self.hass.data[DOMAIN][self._entry.entry_id]["tasks"] = new_tasks_data
                
                _LOGGER.debug("Tasks sensor updated with %d tasks", len(tasks_list))
                
        except Exception as err:
            _LOGGER.error("Error updating tasks sensor: %s", err)