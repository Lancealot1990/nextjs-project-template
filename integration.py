import asyncio
import socket
from typing import Dict, Any, List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base.base_integration import BaseIntegration

class GlobalCacheItachIntegration(BaseIntegration):
    """Global Cache iTach IP to Serial/IR/Relay Bridge Integration"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.socket = None
        self.connected = False
        
    def get_metadata(self):
        return {
            "id": "global_cache_itach",
            "name": "Global Cache iTach",
            "version": "1.0",
            "author": "Empire Audio",
            "description": "IP to Serial/IR/Relay Bridge",
            "icon": "",
            "category": "bridge",
            "type": "globalcache",  
            "connection_types": ["tcp"],
            "capabilities": {
                "bridge": True,
                "serial": True,
                "ir": True,
                "relay": True,
                "discovery": True
            },
            "device_template": {
                "type": "globalcache",
                "category": "bridge"
            }
        }
    
    def get_zone_template(self):
        """iTach doesn't have zones, it's a bridge"""
        return ""
    
    def get_widgets(self):
        """Return bridge status widget"""
        return [
            {
                "id": "itach_status",
                "name": "Bridge Status",
                "icon": "",
                "type": "status",
                "integration": "global_cache_itach",
                "template": '''
                <div class="bridge-status-widget" data-integration="global_cache_itach" data-device="{device_id}">
                    <h3>iTach Bridge: {device_name}</h3>
                    <div class="status-indicator" id="status_{device_id}">
                        <span class="status-dot"></span>
                        <span class="status-text">Checking...</span>
                    </div>
                    <div class="bridge-info">
                        <p>IP: {host}:{port}</p>
                        <p>Type: {bridge_type}</p>
                        <p>Model: Global Cache iTach</p>
                    </div>
                    <div class="bridge-actions">
                        <a href="http://{host}" target="_blank" class="btn btn-primary btn-sm">Configure</a>
                    </div>
                </div>
                ''',
                "default_config": {
                    "bridge_type": "IP2SL"
                },
                "requires_device": True
            }
        ]
    
    async def connect(self):
        """Connect to iTach device"""
        host = self.config['connection']['host']
        port = self.config['connection'].get('port', 4999)
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((host, port))
            self.connected = True
            print(f"Connected to iTach at {host}:{port}")
            
            # Get device info
            self.socket.send(b"getversion\r")
            response = self.socket.recv(1024).decode()
            print(f"iTach version: {response}")
            
        except Exception as e:
            print(f"iTach connection failed: {e}")
            self.connected = False
            raise
    
    async def disconnect(self):
        """Disconnect from iTach"""
        if self.socket:
            self.socket.close()
            self.connected = False
    
    async def handle_command(self, command: str, zone: str, value: Any):
        """Handle bridge commands"""
        if command == "send_serial":
            # Format: send_serial,<module>:<port>,<data>
            await self.send_serial(value)
        elif command == "send_ir":
            # Format: sendir,<module>:<port>,<ir_data>
            await self.send_ir(value)
    
    async def send_serial(self, data: str):
        """Send serial data through iTach"""
        if not self.connected:
            await self.connect()
        
        try:
            self.socket.send(data.encode())
            response = self.socket.recv(1024).decode()
            return response
        except Exception as e:
            print(f"iTach send error: {e}")
            self.connected = False
            raise
    
    async def send_ir(self, data: str):
        """Send IR command through iTach"""
        if not self.connected:
            await self.connect()
        
        try:
            command = f"sendir,{data}\r"
            self.socket.send(command.encode())
            response = self.socket.recv(1024).decode()
            return response
        except Exception as e:
            print(f"iTach IR error: {e}")
            raise
    
    @staticmethod
    async def discover_devices(timeout: int = 5) -> List[Dict[str, Any]]:
        """Discover iTach devices on the network"""
        devices = []
        
        # iTach discovery uses UDP broadcast
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1)
        
        try:
            # Send discovery beacon
            sock.sendto(b"AMXB<-UUID=GlobalCache_", ('<broadcast>', 9131))
            
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = data.decode('utf-8')
                    
                    # Parse response
                    if "AMXB" in response:
                        device_info = {
                            "ip": addr[0],
                            "port": 4999,
                            "model": "Unknown",
                            "uuid": "Unknown",
                            "name": f"iTach at {addr[0]}",
                            "integration": "global_cache_itach",
                            "type": "globalcache",
                            "category": "bridge"
                        }
                        
                        # Extract model and UUID from response
                        parts = response.split('-')
                        for part in parts:
                            if "UUID=" in part:
                                device_info["uuid"] = part.split('=')[1]
                            elif "Model=" in part:
                                device_info["model"] = part.split('=')[1]
                                device_info["name"] = f"iTach {device_info['model']} at {addr[0]}"
                        
                        devices.append(device_info)
                        
                except socket.timeout:
                    continue
                    
        finally:
            sock.close()
        
        return devices
    
    async def handle_mqtt_message(self, topic: str, payload: str):
        """Handle MQTT messages for bridge commands"""
        parts = topic.split('/')
        if len(parts) >= 4 and parts[0] == 'bridges':
            command = parts[2]
            if command == 'serial':
                await self.send_serial(payload)

# Factory function
def create_integration(config: Dict[str, Any]) -> BaseIntegration:
    return GlobalCacheItachIntegration(config)
