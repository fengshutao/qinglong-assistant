"""Button platform for QingLong integration."""

from __future__ import annotations
import logging
import time
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up QingLong button entities from a config entry."""
    
    data = hass.data[DOMAIN][entry.entry_id]
    client = data.get("client")
    host = data.get("host")
    port = data.get("port")
    
    # Create button entity
    button_entity = QingLongRerunButton(entry, client, host, port)
    async_add_entities([button_entity], True)


class QingLongRerunButton(ButtonEntity):
    """Representation of a QingLong rerun button."""
    
    def __init__(self, entry: ConfigEntry, client, host: str, port: int):
        """Initialize the button."""
        self._entry = entry
        self._client = client
        self._host = host
        self._port = port
        self._last_press_time = 0
        
        # Entity properties
        self._attr_name = "重新运行"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_rerun_button"
        self._attr_icon = "mdi:replay"
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"青龙面板 ({host}:{port})",
            "manufacturer": "青龙面板",
            "model": "QingLong",
        }
    
    async def async_press(self) -> None:
        """Handle the button press."""
        current_time = time.time()
        
        # 防止过于频繁的点击（至少间隔2秒）
        if current_time - self._last_press_time < 2:
            _LOGGER.warning("Button pressed too frequently, ignoring")
            return
            
        self._last_press_time = current_time
        
        # 获取当前选择的任务
        data = self.hass.data[DOMAIN][self._entry.entry_id]
        selected_task = data.get("selected_task")
        
        if not selected_task or "task_id" not in selected_task:
            _LOGGER.warning("No task selected, please select a task first")
            return
        
        task_id = selected_task["task_id"]
        option = selected_task.get("option", "未知任务")
        
        _LOGGER.info("Re-running task: %s (ID: %s)", option, task_id)
        
        # 运行状态跟踪
        run_status = {
            "task_name": option,
            "status": "running",
            "start_time": current_time,
            "result": None,
            "error": None
        }
        
        # 调用API运行任务
        success = await self._client.async_run_task(task_id)
        
        run_status["end_time"] = time.time()
        
        if success:
            _LOGGER.info("Task %s re-run successfully", option)
            run_status["status"] = "success"
            run_status["result"] = "任务已重新启动"
            
            # 任务运行成功后，更新选择状态
            self.hass.data[DOMAIN][self._entry.entry_id]["selected_task"]["timestamp"] = current_time
            self.hass.data[DOMAIN][self._entry.entry_id]["selected_task"]["run_status"] = run_status
        else:
            _LOGGER.error("Failed to re-run task %s", option)
            run_status["status"] = "failed"
            run_status["error"] = "API调用失败"
        
        # 更新状态
        self.async_write_ha_state()
        
        # 记录按钮按下时间
        self._attr_extra_state_attributes = {
            "last_press_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time)),
            "last_selected_task": option,
            "last_task_id": task_id,
            "last_run_status": run_status["status"],
        }
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "host": self._host,
            "port": self._port,
            "description": "重新运行当前选择的任务",
        }
        
        # 添加当前选择的任务信息
        data = self.hass.data[DOMAIN][self._entry.entry_id]
        selected_task = data.get("selected_task")
        
        if selected_task:
            attrs.update({
                "last_selected_task": selected_task.get("option", "无"),
                "last_selected_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(selected_task.get("timestamp", 0))),
                "task_id": selected_task.get("task_id", "无"),
            })
            
            if "run_status" in selected_task:
                run_status = selected_task["run_status"]
                attrs.update({
                    "last_run_status": run_status.get("status", "未知"),
                    "last_run_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run_status.get("start_time", 0))),
                })
        
        # 添加上次按下时间
        if self._last_press_time > 0:
            attrs["last_press_time"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_press_time))
        
        return attrs