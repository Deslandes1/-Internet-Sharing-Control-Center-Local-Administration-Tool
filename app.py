import streamlit as st
import subprocess
import re
import os
import tempfile
import time

st.set_page_config(
    page_title="Internet Sharing Control Center",
    page_icon="🌐",
    layout="wide"
)

# ----- Helper functions -----
def run_cmd(cmd, shell=False):
    """Run a command and return (stdout, stderr, returncode)."""
    try:
        if shell:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), -1

def wg_installed():
    """Check if WireGuard is installed (by checking wg command)."""
    stdout, stderr, code = run_cmd(["wg", "--version"])
    return code == 0

def tunnel_service_exists(name="wg0"):
    """Check if the tunnel service exists (Windows)."""
    stdout, stderr, code = run_cmd(f"sc query {name}", shell=True)
    return code == 0 and "does not exist" not in stderr

def start_tunnel(name="wg0"):
    """Start the WireGuard tunnel service."""
    if not tunnel_service_exists(name):
        return False, "Tunnel service not installed. Please install the tunnel first."
    stdout, stderr, code = run_cmd(f"net start {name}", shell=True)
    if code == 0:
        return True, "Tunnel started successfully."
    else:
        return False, f"Failed to start tunnel: {stderr}"

def stop_tunnel(name="wg0"):
    """Stop the WireGuard tunnel service."""
    if not tunnel_service_exists(name):
        return False, "Tunnel service not installed."
    stdout, stderr, code = run_cmd(f"net stop {name}", shell=True)
    if code == 0:
        return True, "Tunnel stopped successfully."
    else:
        return False, f"Failed to stop tunnel: {stderr}"

def get_tunnel_status(name="wg0"):
    """Get current status of the tunnel service."""
    if not tunnel_service_exists(name):
        return "Not installed"
    stdout, stderr, code = run_cmd(f"sc query {name}", shell=True)
    if code != 0:
        return "Unknown"
    if "RUNNING" in stdout:
        return "Running"
    elif "STOPPED" in stdout:
        return "Stopped"
    else:
        return "Unknown"

def get_wg_show():
    """Run wg show and parse output."""
    stdout, stderr, code = run_cmd(["wg", "show"])
    if code != 0:
        return None, stderr
    return stdout, None

def parse_wg_show(output):
    """Parse wg show output into a dict of peers."""
    peers = []
    if not output:
        return peers
    sections = re.split(r'peer:\s*([a-zA-Z0-9+/=]+)', output)
    for i in range(1, len(sections), 2):
        pubkey = sections[i]
        rest = sections[i+1].strip()
        endpoint = ""
        allowed_ips = ""
        latest_handshake = ""
        transfer_rx = ""
        transfer_tx = ""
        for line in rest.split('\n'):
            if "endpoint" in line:
                endpoint = line.split(':', 1)[-1].strip()
            if "allowed ips" in line:
                allowed_ips = line.split(':', 1)[-1].strip()
            if "latest handshake" in line:
                latest_handshake = line.split(':', 1)[-1].strip()
            if "transfer" in line:
                parts = line.split(':')[1].strip().split(',')
                if len(parts) >= 2:
                    rx_part = parts[0].strip()
                    tx_part = parts[1].strip()
                    if "received" in rx_part:
                        transfer_rx = rx_part.replace("received", "").strip()
                    else:
                        transfer_rx = rx_part
                    if "sent" in tx_part:
                        transfer_tx = tx_part.replace("sent", "").strip()
                    else:
                        transfer_tx = tx_part
        peers.append({
            "public_key": pubkey,
            "endpoint": endpoint,
            "allowed_ips": allowed_ips,
            "latest_handshake": latest_handshake,
            "rx": transfer_rx,
            "tx": transfer_tx
        })
    return peers

def generate_client_config(server_public_key, server_endpoint, client_private_key, client_address="10.0.0.2/32", dns="1.1.1.1"):
    config = f"""[Interface]
PrivateKey = {client_private_key}
Address = {client_address}
DNS = {dns}

[Peer]
PublicKey = {server_public_key}
Endpoint = {server_endpoint}
AllowedIPs = 0.0.0.0/0
"""
    return config

# ----- App UI -----
st.title("🌐 Internet Sharing Control Center")
st.markdown("Manage your WireGuard VPN server to share your internet connection.")

if not wg_installed():
    st.error("WireGuard is not installed or not in PATH. Please install WireGuard from https://www.wireguard.com/install/")
    st.stop()

with st.sidebar:
    st.markdown("## 📖 Instructions")
    st.markdown("""
    1. **Install WireGuard** on your Windows machine.
    2. **Create a tunnel configuration** (e.g., `wg0.conf`) and place it in `%ProgramFiles%\\WireGuard\\`.
    3. **Install the tunnel as a service** using:
