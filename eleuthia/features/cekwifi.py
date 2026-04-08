import paramiko
import re
import time

# Device list — tambah/kurangi di sini
DEVICES = [
    {"name": "Server Wrj", "ip": "192.168.9.150"},
    {"name": "Client Ant", "ip": "192.168.9.151"}
]
SSH_USER = "admin"
SSH_PASS = "Indonesia2019"


def get_mca_data(ip, user, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip, username=user, password=password, timeout=10,
            allow_agent=False, look_for_keys=False,
            disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']}
        )
        
        stdin, stdout, stderr = client.exec_command('mca-status')
        out1 = stdout.read().decode()
        t1 = time.time()
        
        time.sleep(1)
        
        stdin, stdout, stderr = client.exec_command('mca-status')
        out2 = stdout.read().decode()
        t2 = time.time()
        
        client.close()
        
        def extract(text, pattern):
            match = re.search(pattern, text)
            return match.group(1) if match else "0"

        data = {
            'signal': extract(out2, r'signal=(-\d+)'),
            'noise': extract(out2, r'noise=(-\d+)'),
            'uplink_cap': extract(out2, r'wlanUplinkCapacity=(\d+)'),
            'tx_mod': extract(out2, r'txModRate=(\d+x)'),
            'rx_mod': extract(out2, r'rxModRate=(\d+x)'),
            'lan_speed': extract(out2, r'lanSpeed=(\d+Mbps)'),
            'mem_free': extract(out2, r'memFree=(\d+)'),
            'latency': extract(out2, r'wlanTxLatency=(\d+)')
        }

        tx_b1, tx_b2 = int(extract(out1, r'wlanTxBytes=(\d+)')), int(extract(out2, r'wlanTxBytes=(\d+)'))
        rx_b1, rx_b2 = int(extract(out1, r'wlanRxBytes=(\d+)')), int(extract(out2, r'wlanRxBytes=(\d+)'))
        
        dt = t2 - t1
        data['thru_tx'] = f"{((tx_b2 - tx_b1) * 8 / (1024*1024) / dt):.2f}"
        data['thru_rx'] = f"{((rx_b2 - rx_b1) * 8 / (1024*1024) / dt):.2f}"
        data['capacity'] = f"{int(data['uplink_cap'])/1000:.1f}"
        data['ram_mb'] = f"{int(data['mem_free'])/1024:.1f}"
        
        return data
    except Exception:
        return None


def run_check():
    """
    Run WiFi check on all devices.
    Returns (table_str, raw_report) for display and LLM analysis.
    """
    cards = ""
    raw_report = ""

    for dev in DEVICES:
        data = get_mca_data(dev['ip'], SSH_USER, SSH_PASS)
        if data:
            mod = f"T{data['tx_mod']}/R{data['rx_mod']}"
            cards += (
                f"📍 <b>{dev['name']}</b>\n"
                f"   Signal: {data['signal']} dBm | Noise: {data['noise']} dBm\n"
                f"   Capacity: {data['capacity']} Mbps\n"
                f"   Throughput: ↑{data['thru_tx']} / ↓{data['thru_rx']} Mbps\n"
                f"   LAN: {data['lan_speed']} | Latency: {data['latency']}ms\n"
                f"   RAM Free: {data['ram_mb']} MB | Mod: {mod}\n\n"
            )
            raw_report += (
                f"{dev['name']}: Signal={data['signal']}dBm, Noise={data['noise']}dBm, "
                f"Capacity={data['capacity']}Mbps, Throughput TX={data['thru_tx']}Mbps RX={data['thru_rx']}Mbps, "
                f"LAN={data['lan_speed']}, Latency={data['latency']}ms, "
                f"RAM Free={data['ram_mb']}MB, Modulation={mod}\n"
            )
        else:
            cards += f"📍 <b>{dev['name']}</b>\n   ❌ OFFLINE / TIMEOUT\n\n"
            raw_report += f"{dev['name']}: OFFLINE / TIMEOUT\n"

    return cards, raw_report


if __name__ == "__main__":
    print("\n" + "="*70)
    cards, _ = run_check()
    print(cards)
    print("="*105)
