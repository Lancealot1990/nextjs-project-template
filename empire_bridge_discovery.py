"""Empire Bridge Discovery Protocol"""
import asyncio
import socket
import json
from typing import List, Dict, Any

class EmpireBridgeDiscovery:
    """Discover Empire Bridge devices on the network"""
    
    @staticmethod
    async def discover(timeout: int = 5) -> List[Dict[str, Any]]:
        """
        Discover Empire Bridge devices using UDP broadcast
        Returns list of discovered bridges
        """
        devices = []
        
        # Create UDP socket for discovery
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', 0))
        sock.settimeout(1)
        
        try:
            # Empire Bridge discovery packet
            discovery_packet = json.dumps({
                "cmd": "discover",
                "type": "empire_bridge"
            }).encode()
            
            # Broadcast on common ports
            for port in [8888, 9999, 5000]:
                try:
                    sock.sendto(discovery_packet, ('<broadcast>', port))
                except:
                    pass
            
            # Listen for responses
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = json.loads(data.decode('utf-8'))
                    
                    if response.get('type') == 'empire_bridge':
                        device = {
                            "name": response.get('name', 'Empire Bridge'),
                            "ip": addr[0],
                            "port": response.get('port', 5000),
                            "model": response.get('model', 'Unknown'),
                            "version": response.get('version', 'Unknown'),
                            "serial": response.get('serial', 'Unknown'),
                            "capabilities": response.get('capabilities', [])
                        }
                        devices.append(device)
                        
                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"Discovery error: {e}")
                    
        finally:
            sock.close()
        
        return devices

    @staticmethod
    async def discover_all_bridges(timeout: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Discover all types of bridges (Empire, iTach, etc.)"""
        results = {
            "empire": [],
            "itach": [],
            "other": []
        }
        
        # Discover Empire bridges
        results["empire"] = await EmpireBridgeDiscovery.discover(timeout)
        
        # Discover iTach devices
        try:
            from integrations.global_cache_itach.integration import GlobalCacheItachIntegration
            results["itach"] = await GlobalCacheItachIntegration.discover_devices(timeout)
        except:
            pass
        
        return results
