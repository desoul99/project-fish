from typing import Optional
import yaml
import nodriver
from nodriver import cdp
from model.model import EmulationDevice, EmulationConfig


class Emulation:
    def __init__(self, config: EmulationConfig) -> None:
        self.emulation_devices: list[EmulationDevice] = []
        self.config: EmulationConfig = config
        # Load config
        with open(self.config.emulation_config, "r") as f_obj:
            data = yaml.safe_load(f_obj)
            if "devices" in data:
                for device in data["devices"]:
                    self.emulation_devices.append(EmulationDevice.from_dict(device))

    def get_device_by_name(self, name: str) -> Optional[EmulationDevice]:
        """Retrieve an EmulationDevice by its name."""
        for device in self.emulation_devices:
            if device.name == name:
                return device
        return None

    @staticmethod
    async def setup_emulation_monitoring(tab: nodriver.Tab, emulation_device: EmulationDevice) -> None:
        await tab.send(cdp.emulation.set_device_metrics_override(**emulation_device.device_metrics.to_dict()))
        await tab.send(cdp.network.set_user_agent_override(**emulation_device.user_agent_override.to_dict()))
        await tab.send(cdp.emulation.set_user_agent_override(**emulation_device.user_agent_override.to_dict()))
        if emulation_device.device_metrics.mobile:
            await tab.send(cdp.emulation.set_touch_emulation_enabled(enabled=True))
        if emulation_device.accepted_encodings:
            await tab.send(cdp.network.set_accepted_encodings(emulation_device.accepted_encodings))
