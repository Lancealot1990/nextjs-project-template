"""Bose EX440 v3 Integration
This new-style integration follows a lightweight "links" concept inspired by
Home-Assistant entities.  Each Link is a logical control (volume slider, mute
button, source selector) that can be attached to a Zone card in the UI.

Only the minimal contract needed by the existing backend is implemented.  The
UI can fetch metadata via `get_metadata()` and the list of available links via
`get_links()`.  Commands are routed through `handle_link_command()` which in
turn calls `send_command()` using the currently-configured connection (serial,
TCP, or an external bridge).
"""

from __future__ import annotations

import asyncio
import os
import sys
import socket
import serial
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

# Make sure the parent folder is on path so we can import the base class.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    # Try direct import first
    from base.base_integration import BaseIntegration  # noqa: E402
except ImportError:
    # Fall back to relative import
    try:
        from ..base.base_integration import BaseIntegration  # noqa: E402
    except ImportError:
        # Last resort: absolute import with full path
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "BaseIntegration", 
            os.path.join(ROOT, "base", "base_integration.py")
        )
        base_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base_module)
        BaseIntegration = base_module.BaseIntegration

# ---------------------------------------------------------------------------
# Dataclasses / helpers
# ---------------------------------------------------------------------------

@dataclass
class Link:
    """A lightweight entity describing a single control.

    type:     slider | button | select
    command:  Internal identifier used by the integration when a value is set
    options:  (select only) list of label/value pairs
    """

    id: str
    name: str
    type: str  # slider, button, select
    command: str
    min: Optional[int] = None  # slider only
    max: Optional[int] = None  # slider only
    step: Optional[int] = None  # slider only
    options: Optional[List[Dict[str, Any]]] = None  # select only

    def as_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Integration Implementation
# ---------------------------------------------------------------------------

class BoseEX440V3Integration(BaseIntegration):
    """Integration that exposes EX440 controls via Links."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.serial_conn = None
        self.reader = None
        self.writer = None

    # --------------------------- Metadata & Links -------------------------
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "id": "bose_ex440_v3",
            "name": "Bose EX440 (v3)",
            "version": "3.0",
            "author": "Empire Audio",
            "description": "4×4 DSP Audio Processor (link-based)",
            "icon": "🔊",
            "category": "audio",
            "connection_types": ["serial", "tcp", "bridge"],
        }

    def get_links(self) -> List[Dict[str, Any]]:
        """Return the list of link definitions as dictionaries."""
        links = []
        
        # Get zones from config
        zones = self.config.get('zones', [])
        
        # If no zones defined, create a default "master" zone
        if not zones:
            zones = [{"id": "master", "name": "Master", "volume_module": "Main Volume", "mute_module": "Main Volume", "source_module": "Selector 1"}]
        
        # Generate links for each zone
        for zone in zones:
            zone_id = zone['id']
            zone_name = zone['name']
            volume_module = zone.get('volume_module', 'Main Volume')
            mute_module = zone.get('mute_module', 'Main Volume')
            source_module = zone.get('source_module', 'Selector 1')
            
            # Volume slider for this zone
            links.append(
                Link(
                    id=f"{zone_id}_volume",
                    name=f"{zone_name} Volume",
                    type="slider",
                    command="set_volume",
                    min=-60,
                    max=12,
                    step=0.5,
                ).as_dict()
            )
            
            # Mute toggle for this zone
            links.append(
                Link(
                    id=f"{zone_id}_mute",
                    name=f"{zone_name} Mute",
                    type="button",
                    command="toggle_mute",
                ).as_dict()
            )
            
            # Source select for this zone
            links.append(
                Link(
                    id=f"{zone_id}_source",
                    name=f"{zone_name} Source",
                    type="select",
                    command="set_source",
                    options=[
                        {"label": "Input 1", "value": 1},
                        {"label": "Input 2", "value": 2},
                        {"label": "Input 3", "value": 3},
                        {"label": "Input 4", "value": 4},
                    ],
                ).as_dict()
            )
        
        return links

    # --------------------------- UI Templates ----------------------------
    # For now we defer zone-template rendering to the existing v2
    def get_zone_template(self) -> str:  # noqa: D401
        """Return an empty template – UI will assemble cards from Links."""
        return ""

    def get_widgets(self) -> List[Dict[str, Any]]:
        # No drawer widgets yet – just return empty list
        return []

    # --------------------------- Connection Mgmt -------------------------
    async def connect(self):
        """Establish connection (serial / tcp)."""
        conn_type = self.config.get('connection', {}).get('type', 'serial')
        
        if conn_type == 'serial':
            await self._connect_serial()
        elif conn_type == 'tcp':
            await self._connect_tcp()
        elif conn_type == 'bridge':
            # Bridge connection handled via MQTT
            pass
            
    async def _connect_serial(self):
        """Connect via serial port"""
        port = self.config['connection']['port']
        baudrate = self.config['connection'].get('baudrate', 9600)
        
        try:
            self.serial_conn = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1,
                write_timeout=1
            )
            print(f"Connected to Bose EX440 on {port}")
        except Exception as e:
            print(f"Serial connection failed: {e}")
            raise
            
    async def _connect_tcp(self):
        """Connect via TCP/IP"""
        host = self.config['connection']['host']
        port = self.config['connection']['port']
        
        try:
            self.reader, self.writer = await asyncio.open_connection(host, port)
            print(f"Connected to Bose EX440 at {host}:{port}")
        except Exception as e:
            print(f"TCP connection failed: {e}")
            raise

    async def disconnect(self):
        """Disconnect from device"""
        if hasattr(self, 'serial_conn') and self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
            
        if hasattr(self, 'writer') and self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
            self.reader = None
            
    def get_zone_config(self, zone_id: str) -> Dict[str, Any]:
        """Get zone configuration by ID."""
        zones = self.config.get('zones', [])
        for zone in zones:
            if zone.get('id') == zone_id:
                return zone
        return None

    # --------------------------- Command Handling ------------------------
    async def handle_link_command(self, link_id: str, value: Any):
        """Public entrypoint the UI will call when a link changes state."""
        # Parse zone_id and command from link_id (format: zone_id_command)
        parts = link_id.split('_', 1)
        if len(parts) != 2:
            print(f"Invalid link_id format: {link_id}")
            return
            
        zone_id, command = parts
        
        # Get zone configuration
        zone_config = self.get_zone_config(zone_id)
        if not zone_config:
            print(f"Zone not found: {zone_id}")
            return
            
        # Get module names for this zone
        volume_module = zone_config.get('volume_module', 'Main Volume')
        mute_module = zone_config.get('mute_module', 'Main Volume')
        source_module = zone_config.get('source_module', 'Selector 1')
        
        # Handle command based on the command type
        if command == "volume" or command == "set_volume":
            await self._cmd_set_volume(zone_id, volume_module, float(value))
        elif command == "mute" or command == "toggle_mute":
            await self._cmd_toggle_mute(zone_id, mute_module, bool(value))
        elif command == "source" or command == "set_source":
            await self._cmd_set_source(zone_id, source_module, int(value))

    # Legacy compatibility – route UI/ MQTT commands to link-handler
    async def handle_command(self, command: str, zone: str, value: Any):
        # Format the link_id as zone_command
        link_id = f"{zone}_{command}"
        await self.handle_link_command(link_id, value)

    async def handle_mqtt_message(self, topic: str, payload: str):
        # Not implemented yet – future MQTT integration.
        pass

    # --------------------------- Device Commands -------------------------
    async def _cmd_set_volume(self, zone_id: str, module_name: str, level_db: float):
        # Ensure level is within valid range (-60.5 to +12.0 dB)
        level_db = max(-60.5, min(12.0, level_db))
        
        # Format the command: SA"Module Name">1>value<CR>
        cmd = f'SA"{module_name}">1>{level_db}<CR>'
        await self.send_command(cmd)
        self.publish_state(zone_id, "volume", level_db)

    async def _cmd_toggle_mute(self, zone_id: str, module_name: str, mute: bool):
        # Format the command: SA"Module Name">2>value<CR>
        # O=On (muted), F=Off (unmuted)
        mute_value = "O" if mute else "F"
        cmd = f'SA"{module_name}">2>{mute_value}<CR>'
        await self.send_command(cmd)
        self.publish_state(zone_id, "mute", mute)

    async def _cmd_set_source(self, zone_id: str, module_name: str, source_num: int):
        # Ensure source number is within valid range (1-16)
        source_num = max(1, min(16, source_num))
        
        # Format the command: SA"Module Name">1>value<CR>
        cmd = f'SA"{module_name}">1>{source_num}<CR>'
        await self.send_command(cmd)
        self.publish_state(zone_id, "source", source_num)

    # --------------------------- Low-level send --------------------------
    async def send_command(self, command: str):
        """Send command via appropriate connection"""
        # Convert <CR> to actual carriage return
        command = command.replace("<CR>", "\r")
        
        conn_type = self.config.get('connection', {}).get('type', 'serial')
        
        # Ensure we have a connection
        if not hasattr(self, 'serial_conn') and not hasattr(self, 'writer'):
            await self.connect()
        
        if conn_type == 'serial' and hasattr(self, 'serial_conn') and self.serial_conn:
            self.serial_conn.write(command.encode())
        elif conn_type == 'tcp' and hasattr(self, 'writer') and self.writer:
            self.writer.write(command.encode())
            await self.writer.drain()
        elif conn_type == 'bridge':
            # Send via MQTT to bridge
            if self.mqtt_client:
                bridge_topic = f"bridges/{self.config['connection']['bridge_id']}/command"
                self.mqtt_client.publish(bridge_topic, command)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_integration(config: Dict[str, Any]):  # noqa: D401
    return BoseEX440V3Integration(config)
