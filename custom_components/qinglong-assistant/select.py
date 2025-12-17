"""Select platform for QingLong integration."""

from __future__ import annotations
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# 轮询间隔 - 30秒
SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up QingLong select entities from a config entry."""
    
    data = hass.data[DOMAIN][entry.entry_id]
    client = data.get("client")
    host = data.get("host")
    port = data.get("port")
    tasks_data = data.get("tasks", {})
    
    # Create select entity
    select_entity = QingLongTaskSelect(entry, client, host, port, tasks_data)
    async_add_entities([select_entity], True)


class QingLongTaskSelect(SelectEntity):
    """Representation of a QingLong task select."""
    
    # 设置轮询间隔
    _attr_should_poll = True
    
    def __init__(self, entry: ConfigEntry, client, host: str, port: int, tasks_data: dict):
        """Initialize the select."""
        self._entry = entry
        self._client = client
        self._host = host
        self._port = port
        self._tasks_data = tasks_data
        self._last_update = 0
        
        # Entity properties
        self._attr_name = "运行定时任务"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_run_task"
        self._attr_icon = "mdi:play"
        
        # Select properties
        self._options = []
        self._current_option = None
        self._task_mapping = {}  # 存储command到task_id的映射
        
        # Device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"青龙面板 ({host}:{port})",
            "manufacturer": "青龙面板",
            "model": "QingLong",
        }
    
    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        # 现在self.hass已经可用，可以更新选项
        self._update_options()
    
    def _update_options(self):
        """Update select options from tasks data."""
        if not self._client:
            return
        
        # 从hass.data获取最新的tasks_data
        if DOMAIN in self.hass.data and self._entry.entry_id in self.hass.data[DOMAIN]:
            tasks_data = self.hass.data[DOMAIN][self._entry.entry_id].get("tasks", {})
        else:
            tasks_data = self._tasks_data
        
        # 提取已启用的任务 (isDisabled: 0)
        enabled_tasks = []
        self._task_mapping = {}
        
        if isinstance(tasks_data, dict) and "data" in tasks_data:
            inner_data = tasks_data["data"]
            
            # 获取任务数组
            if isinstance(inner_data, dict) and "data" in inner_data:
                tasks_list = inner_data.get("data", [])
            elif isinstance(inner_data, list):
                tasks_list = inner_data
            else:
                tasks_list = []
            
            for task in tasks_list:
                if isinstance(task, dict) and task.get("isDisabled") == 0:
                    task_id = str(task.get("id"))
                    command = task.get("command", "")
                    
                    # 从command中提取脚本名称（去掉前面的"task "）
                    if command.startswith("task "):
                        script_name = command[5:]  # 去掉"task "前缀
                    else:
                        script_name = command
                    
                    enabled_tasks.append(script_name)
                    self._task_mapping[script_name] = {
                        "task_id": task_id,
                        "command": command,
                        "name": task.get("name", "未命名任务"),
                    }
        
        # 排序并设置选项
        self._options = sorted(enabled_tasks)
        self._attr_options = self._options
        
        # 如果没有当前选择，选择第一个选项
        if not self._current_option and self._options:
            self._current_option = self._options[0]
            self._attr_current_option = self._current_option
    
    @property
    def options(self) -> list[str]:
        """Return the available options."""
        return self._attr_options
    
    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        return self._attr_current_option
    
    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        if option not in self._options:
            raise ValueError(f"Invalid option: {option}")
        
        self._current_option = option
        self._attr_current_option = option
        
        # 运行状态跟踪
        run_status = {
            "task_name": option,
            "status": "running",
            "start_time": time.time(),
            "result": None,
            "error": None
        }
        
        # 运行选中的任务
        if option in self._task_mapping:
            task_info = self._task_mapping[option]
            task_id = task_info["task_id"]
            
            _LOGGER.info("Running task: %s (ID: %s)", option, task_id)
            
            # 调用API运行任务
            success = await self._client.async_run_task(task_id)
            
            run_status["end_time"] = time.time()
            
            if success:
                _LOGGER.info("Task %s started successfully", option)
                run_status["status"] = "success"
                run_status["result"] = "任务已启动"
            else:
                _LOGGER.error("Failed to start task %s", option)
                run_status["status"] = "failed"
                run_status["error"] = "API调用失败"
            
            # 存储选择
            self.hass.data[DOMAIN][self._entry.entry_id]["selected_task"] = {
                "option": option,
                "task_id": task_id,
                "timestamp": time.time(),
                "run_status": run_status
            }
        
        # 更新状态
        self.async_write_ha_state()
    
    async def async_update(self) -> None:
        """Update select options."""
        current_time = time.time()
        
        # 检查是否需要更新（避免过于频繁的API调用）
        if current_time - self._last_update < 30:
            return
            
        if self._client:
            # 获取最新的任务数据
            try:
                new_tasks_data = await self._client.async_get_tasks()
                self._last_update = current_time
                
                if new_tasks_data:
                    # 更新存储的数据
                    self.hass.data[DOMAIN][self._entry.entry_id]["tasks"] = new_tasks_data
                    
                    # 更新选项
                    self._update_options()
                    
                    # 如果当前选项不在新选项中，重置为第一个选项
                    if self._current_option and self._current_option not in self._options:
                        if self._options:
                            self._current_option = self._options[0]
                            self._attr_current_option = self._current_option
                        else:
                            self._current_option = None
                            self._attr_current_option = None
                            
                    # 记录更新状态
                    _LOGGER.debug("Task select updated with %d options", len(self._options))
            except Exception as err:
                _LOGGER.error("Error updating task select: %s", err)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "host": self._host,
            "port": self._port,
            "last_updated": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            "polling_interval": "30秒",
            "available_tasks": len(self._options),
        }
        
        # 添加最近运行任务的状态
        selected_task = self.hass.data[DOMAIN][self._entry.entry_id].get("selected_task")
        if selected_task:
            attrs["last_selected_task"] = selected_task["option"]
            attrs["last_selected_time"] = time.strftime('%Y-%m-%d %H:%M:%S', 
                                                       time.localtime(selected_task["timestamp"]))
            
            if "run_status" in selected_task:
                run_status = selected_task["run_status"]
                attrs["last_run_status"] = run_status["status"]
                attrs["last_run_start"] = time.strftime('%Y-%m-%d %H:%M:%S', 
                                                       time.localtime(run_status.get("start_time", 0)))
                attrs["last_run_duration"] = f"{run_status.get('end_time', 0) - run_status.get('start_time', 0):.2f}秒"
                if run_status.get("error"):
                    attrs["last_run_error"] = run_status["error"]
        
        if self._current_option and self._current_option in self._task_mapping:
            task_info = self._task_mapping[self._current_option]
            attrs.update({
                "task_id": task_info["task_id"],
                "command": task_info["command"],
                "task_name": task_info["name"],
            })
            
        return attrs