import os
import socket
import struct
import time
import select

class SimpleRcon:
    """
    A thread-safe RCON client that avoids using implementation-specific signals.
    """
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
        self.request_id = 1

    def __enter__(self):
        self.connect()
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(60) # Increased timeout for heavy operations
        self.socket.connect((self.host, self.port))

    def login(self):
        # Type 3 = Login
        self._send(3, self.password)
        r_type, r_id, r_body = self._read()
        if r_id == -1:
            raise ConnectionError("RCON Login Failed: Invalid Password")

    def command(self, cmd):
        # Type 2 = Command
        self._send(2, cmd)
        r_type, r_id, r_body = self._read()
        return r_body

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def _send(self, typ, data):
        # Packet structure:
        # Length (4 bytes): ID (4) + Type (4) + Body (len) + 2 nulls
        # ID (4 bytes)
        # Type (4 bytes)
        # Body (utf-8 string)
        # Null (1 byte)
        # Null (1 byte)
        
        body = data.encode('utf-8')
        length = 4 + 4 + len(body) + 2
        
        # Pack: Length, ID, Type
        # Note: struct.pack('<iii'...) packs 3 integers (12 bytes)
        header = struct.pack('<iii', length, self.request_id, typ)
        
        packet = header + body + b'\x00\x00'
        
        self.socket.sendall(packet)

    def _read(self):
        # Read Length (4 bytes)
        header = self._recv_bytes(4)
        if not header:
            return 0, 0, ""
        length = struct.unpack('<i', header)[0]
        
        # Read Rest (Length bytes)
        # Payload: ID(4) + Type(4) + Body + Null
        payload = self._recv_bytes(length)
        
        r_id = struct.unpack('<i', payload[0:4])[0]
        r_type = struct.unpack('<i', payload[4:8])[0]
        
        # Body is from 8 to end-2 (since last 2 are nulls usually, but strictly it's null terminated)
        # Python RCON usually just strips nulls
        r_body = payload[8:-2].decode('utf-8', errors='ignore')
        
        return r_type, r_id, r_body

    def _recv_bytes(self, n):
        data = b''
        while len(data) < n:
            chunk = self.socket.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data


class RconClient:
    def __init__(self):
        self.host = os.getenv("RCON_HOST", "localhost")
        self.port = int(os.getenv("RCON_PORT", 28889))
        self.password = os.getenv("RCON_PASSWORD", "")
        
    def connect_and_send(self, commands):
        """
        Connects to RCON, sends a list of commands, and disconnects.
        commands: list of command strings (e.g. ["/say hello", "/setblock ..."])
        """
        if not self.password:
            raise ValueError("RCON_PASSWORD not set in .env")
            
        response_log = []
        
        try:
            with SimpleRcon(self.host, self.port, self.password) as mcr:
                for cmd in commands:
                    resp = mcr.command(cmd)
                    if resp:
                        # Clean up Minecraft formatting codes if needed
                        response_log.append(resp)
                    
                    # Small delay to prevent overwhelming the server with requests
                    # Reduced to 0.01s for optimized flow
                    time.sleep(0.01)
        except Exception as e:
            raise ConnectionError(f"RCON Connection Failed: {e}")
            
        return response_log

    def build_voxels(self, blocks, origin=None):
        """
        Generates and executes setblock commands for the given voxel blocks.
        Optimized using RLE (Run Length Encoding) to use /fill for contiguous blocks.
        """
        import itertools
        
        commands = []
        
        # Feedback off
        commands.append("gamerule sendCommandFeedback false")
        
        if not blocks:
            return []
            
        # Sort blocks to enable RLE: Type -> Y -> Z -> X
        # This groups blocks that are on the same row (Y, Z) and same material.
        sorted_blocks = sorted(blocks, key=lambda b: (b['type'], b['y'], b['z'], b['x']))
        
        count_cmds = 0
        
        # Group by Type, Y, Z
        for key, group in itertools.groupby(sorted_blocks, key=lambda b: (b['type'], b['y'], b['z'])):
             b_type, b_y, b_z = key
             row = list(group) # List of blocks in this row (sorted by X)
             
             run_start = row[0]['x']
             run_end = row[0]['x']
             
             for i in range(1, len(row)):
                 cx = row[i]['x']
                 if cx == run_end + 1:
                     # Contiguous
                     run_end = cx
                 else:
                     # Break in continuity -> Flush
                     self._append_optimized_cmd(commands, run_start, run_end, b_y, b_z, b_type, origin)
                     run_start = cx
                     run_end = cx
             
             # Flush final run
             self._append_optimized_cmd(commands, run_start, run_end, b_y, b_z, b_type, origin)
            
        commands.append("gamerule sendCommandFeedback true")
        commands.append(f"say Built {len(blocks)} voxels using {len(commands)-2} commands (Optimized)!")
        
        return self.connect_and_send(commands)

    def _append_optimized_cmd(self, cmds_list, x1, x2, y, z, b_type, origin):
        if origin:
            # Absolute
            ox, oy, oz = origin
            fx1, fx2 = ox + x1, ox + x2
            fy = oy + y
            fz = oz + z
            
            if fx1 == fx2:
                 # b_type already includes 'minecraft:' prefix
                 cmd = f"setblock {fx1} {fy} {fz} {b_type}"
            else:
                 cmd = f"fill {fx1} {fy} {fz} {fx2} {fy} {fz} {b_type}"
        else:
            # Relative
            if x1 == x2:
                cmd = f"execute at @p run setblock ~{x1} ~{y} ~{z} {b_type}"
            else:
                cmd = f"execute at @p run fill ~{x1} ~{y} ~{z} ~{x2} ~{y} ~{z} {b_type}"
        
        cmds_list.append(cmd)
