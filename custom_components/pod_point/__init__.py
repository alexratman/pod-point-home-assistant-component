"""
Custom integration to integrate pod_point with Home Assistant.
"""
import asyncio
from datetime import timedelta
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    APP_IMAGE_URL_BASE,
    CONF_EMAIL,
    CONF_HTTP_DEBUG,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_HTTP_DEBUG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup(hass: HomeAssistant, config: Config):
    """Set up this integration using YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    # Defer heavy imports to prevent blocking the main event loop during loader.py
    from podpointclient.client import PodPointClient
    from .coordinator import PodPointDataUpdateCoordinator
    from .services import async_register_services

    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    email = entry.data.get(CONF_EMAIL)
    password = entry.data.get(CONF_PASSWORD)
    session = async_get_clientsession(hass)

    http_debug = entry.options.get(CONF_HTTP_DEBUG, DEFAULT_HTTP_DEBUG)

    def create_client():
        return PodPointClient(
            username=email, password=password, session=session, http_debug=http_debug
        )

    client = await hass.async_add_executor_job(create_client)

    scan_interval = timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    coordinator = PodPointDataUpdateCoordinator(
        hass, client=client, scan_interval=scan_interval
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    files_path = Path(__file__).parent / "static"
    should_cache = False
    if hass.http:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(APP_IMAGE_URL_BASE, str(files_path), should_cache)]
        )

    for platform in PLATFORMS:
        if entry.options.get(platform, True):
            coordinator.platforms.append(platform)

    await hass.config_entries.async_forward_entry_setups(entry, coordinator.platforms)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ],
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    unloaded = await async_unload_entry(hass, entry)
    if unloaded is False:
        _LOGGER.error("Error unloading entry: %s", entry)

    await async_setup_entry(hass, entry)
