"""The QingLong integration."""

from __future__ import annotations
import logging
import time
import aiohttp
import async_timeout
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN, 
    API_CRONS, 
    API_AUTH,
    API_CRONS_RUN,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRES,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SSL,
    CONF_HOST,
    CONF_PORT,
    TOKEN_REFRESH_THRESHOLD,
    TOKEN_EXPIRY_BUFFER,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.BUTTON]


class QingLongClient:
    """Client to interact with QingLong API."""
    
    def __init__(self, host: str, port: int, ssl: bool, token: str, token_expires: int,
                 client_id: str, client_secret: str, hass: HomeAssistant):
        """Initialize the client."""
        self._host = host
        self._port = port
        self._ssl = ssl
        self._token = token
        self._token_expires = token_expires
        self._client_id = client_id
        self._client_secret = client_secret
        self._hass = hass
        self._session = None
        self._base_url = f"{'https' if ssl else 'http'}://{host}:{port}"
        self._refresh_lock = False
        self._last_refresh_time = 0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def _refresh_token_if_needed(self) -> bool:
        """Refresh token if expired or about to expire."""
        current_time = int(time.time())
        
        # 如果token还有效期超过阈值，不需要刷新
        if self._token_expires - current_time > TOKEN_REFRESH_THRESHOLD:
            return True
        
        # 防止同时多个刷新请求
        if self._refresh_lock:
            _LOGGER.debug("Token refresh already in progress")
            return False
        
        # 防止过于频繁的刷新尝试（至少间隔5分钟）
        if current_time - self._last_refresh_time < 300:
            _LOGGER.debug("Token refresh too recent, skipping")
            return False
            
        self._refresh_lock = True
        
        try:
            _LOGGER.info("Refreshing QingLong token (expires in %d seconds)", 
                        self._token_expires - current_time)
            
            session = await self._get_session()
            url = f"{self._base_url}{API_AUTH}"
            params = {
                "client_id": self._client_id,
                "client_secret": self._client_secret
            }
            
            async with async_timeout.timeout(10):
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        _LOGGER.error("Failed to refresh token: HTTP %s", response.status)
                        return False
                    
                    data = await response.json()
                    if data.get("code") != 200:
                        _LOGGER.error("Failed to refresh token: %s", data.get("message"))
                        return False
                    
                    token_data = data.get("data", {})
                    new_token = token_data.get("token")
                    if not new_token:
                        _LOGGER.error("No token in refresh response")
                        return False
                    
                    # 更新token和过期时间
                    expiration = token_data.get("expiration")
                    if expiration and expiration > current_time:
                        self._token_expires = int(expiration)
                        _LOGGER.info("New token expires at: %s (in %d days)", 
                                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._token_expires)),
                                    (self._token_expires - current_time) // 86400)
                    else:
                        # 默认30天有效期
                        self._token_expires = current_time + 2592000  # 30天
                        _LOGGER.warning("No valid expiration in response, using default 30 days")
                    
                    self._token = new_token
                    self._last_refresh_time = current_time
                    
                    _LOGGER.info("Token refreshed successfully")
                    return True
                    
        except Exception as err:
            _LOGGER.error("Error refreshing token: %s", err)
            return False
        finally:
            self._refresh_lock = False
    
    async def async_run_task(self, task_id: str):
        """Run a specific task."""
        try:
            # 先检查并刷新token
            await self._refresh_token_if_needed()
            
            session = await self._get_session()
            url = f"{self._base_url}{API_CRONS_RUN}"
            
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json"
            }
            
            # 根据API文档，请求体应该是包含任务ID的数组
            data = [task_id]
            
            async with async_timeout.timeout(10):
                async with session.put(url, headers=headers, json=data) as response:
                    if response.status == 401:
                        # Token无效，尝试强制刷新
                        _LOGGER.warning("Token invalid, forcing refresh")
                        self._last_refresh_time = 0
                        return False
                    
                    if response.status != 200:
                        _LOGGER.error("Failed to run task: HTTP %s", response.status)
                        return False
                    
                    result = await response.json()
                    if result.get("code") != 200:
                        _LOGGER.error("Failed to run task: %s", result.get("message"))
                        return False
                    
                    _LOGGER.info("Task %s started successfully", task_id)
                    return True
                    
        except Exception as err:
            _LOGGER.error("Error running task: %s", err)
            return False
    
    def get_token_info(self) -> dict:
        """Get token information for sensor."""
        current_time = int(time.time())
        expires_in = self._token_expires - current_time
        
        # 计算剩余天数/小时/分钟
        if expires_in > 0:
            days = expires_in // 86400
            hours = (expires_in % 86400) // 3600
            minutes = (expires_in % 3600) // 60
            seconds = expires_in % 60
            
            if days > 0:
                expires_display = f"{days}天{hours}小时"
            elif hours > 0:
                expires_display = f"{hours}小时{minutes}分钟"
            elif minutes > 0:
                expires_display = f"{minutes}分钟{seconds}秒"
            else:
                expires_display = f"{seconds}秒"
        else:
            expires_display = "已过期"
        
        return {
            "token": self._token,  # 返回完整token，而不是截断的
            "token_expires": self._token_expires,
            "expires_in": expires_in,
            "expires_display": expires_display,
            "expires_at": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._token_expires)) if self._token_expires > 0 else "已过期",
            "is_valid": expires_in > TOKEN_EXPIRY_BUFFER,
            "needs_refresh": expires_in <= TOKEN_REFRESH_THRESHOLD,
            "last_refresh_time": self._last_refresh_time,
        }
    
    async def async_get_tasks(self):
        """Get all tasks from QingLong."""
        try:
            # 先检查并刷新token
            await self._refresh_token_if_needed()
            
            session = await self._get_session()
            url = f"{self._base_url}{API_CRONS}"
            
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json"
            }
            
            async with async_timeout.timeout(10):
                async with session.get(url, headers=headers) as response:
                    if response.status == 401:
                        # Token无效，尝试强制刷新
                        _LOGGER.warning("Token invalid, forcing refresh")
                        self._last_refresh_time = 0
                        return {}
                    
                    if response.status != 200:
                        _LOGGER.error("Failed to get tasks: HTTP %s", response.status)
                        return {}
                    
                    data = await response.json()
                    if data.get("code") != 200:
                        _LOGGER.error("Failed to get tasks: %s", data.get("message"))
                        return {}
                    
                    return data
                    
        except Exception as err:
            _LOGGER.error("Error getting tasks: %s", err)
            return {}
    
    async def async_close(self):
        """Close the client session."""
        if self._session and not self._session.closed:
            await self._session.close()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up QingLong from a config entry."""
    
    host = entry.data.get(CONF_HOST)
    port = entry.data.get(CONF_PORT)
    ssl = entry.data.get(CONF_SSL, False)
    token = entry.data.get(CONF_TOKEN)
    token_expires = entry.data.get(CONF_TOKEN_EXPIRES, 0)
    client_id = entry.data.get(CONF_CLIENT_ID)
    client_secret = entry.data.get(CONF_CLIENT_SECRET)
    
    # Create client
    client = QingLongClient(host, port, ssl, token, token_expires, client_id, client_secret, hass)
    
    # Test connection and get initial data
    tasks_data = {}
    if token:
        try:
            tasks_data = await client.async_get_tasks()
            if tasks_data:
                _LOGGER.info("Successfully connected to QingLong panel")
        except Exception as err:
            _LOGGER.error("Failed to get initial data: %s", err)
    
    # Store data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "host": host,
        "port": port,
        "ssl": ssl,
        "token": token,
        "token_expires": token_expires,
        "client": client,
        "tasks": tasks_data,
        "selected_task": None,  # 存储用户选择的任务
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Close client session
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        client = hass.data[DOMAIN][entry.entry_id].get("client")
        if client:
            await client.async_close()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok
