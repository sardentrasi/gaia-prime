import libtmux
import json
import os
import time
import sys

# Configure basic logging to stdout
print("🔥 GAIA PRIME DYNAMIC BOOTLOADER 🔥")
print("Initializing ignition sequence...")

def load_registry():
    try:
        with open("registry.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Registry not found!")
        return {}

def main():
    server = libtmux.Server()
    
    # Try to find the session
    try:
        session = server.sessions.get(session_name="gaia_net")
    except libtmux.exc.LibTmuxException:
        print("❌ Session 'gaia_net' not found.")
        return
        
    # Enable Pane Titles (Top Border)
    try:
        server.cmd('set', '-g', 'pane-border-status', 'top')
        server.cmd('set', '-g', 'pane-border-format', ' [ #T ] ')
    except Exception as e:
        print(f"⚠️ Failed to set border status: {e}")

    window = session.windows.get(window_name="command_center")
    
    # The pane where this script is running (usually Pane 0)
    # We want to keep this for Mother Gaia
    boot_pane = window.session.active_pane
    if not boot_pane:
        # Fallback if not attached (e.g. detached start)
        boot_pane = window.panes[0]
        
    try:
        boot_pane.cmd('select-pane', '-T', 'Gaia-Prime')
    except Exception as e:
        print(f"⚠️ Failed to set boot pane title: {e}")
    
    print(f"📍 Bootloader running in Pane {boot_pane.index}")
    
    registry = load_registry()
    
    # [CRITICAL FIX] PRE-CREATE SHARED MEMORY CORE
    # This prevents "Split Brain" where Apollo starts before Gaia and can't find the central memory.
    shared_memory_path = os.path.join(os.getcwd(), "memory_core")
    if not os.path.exists(shared_memory_path):
        print(f"🧠 [GENESIS] Pre-creating Shared Memory Core: {shared_memory_path}")
        os.makedirs(shared_memory_path, exist_ok=True)
    
    # Ignite Modules
    for name, config in registry.items():
        # Validate Config Type (Must be Dict, skip Lists like whitelist)
        if not isinstance(config, dict):
            print(f"⏩ Skipping {name} (Configuration/List)")
            continue

        if not config.get("active", False):
            print(f"⚠️ Skipping {name} (Inactive)")
            continue
            
        print(f"🚀 Igniting {name}...")
        
        # FIX: Ghost Log Wiping
        # We wipe .log files to prevent Sentinel from reading old errors
        module_path = os.path.abspath(config['path'])
        log_file = os.path.join(module_path, f"{name}.log")
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
                print(f"   🧹 Wiped old log: {log_file}")
            except Exception as e:
                print(f"   ⚠️ Failed to wipe log: {e}")
        
        # Check if a pane is already running this module could be tricky without tracking.
        # But for 'ignite' we assume fresh start or we just add panels.
        # For simplicity in this phase, we split fresh windows.
        # In a real dynamic system we might check if they exist, but Tmux panes don't have IDs we persisted easily 
        # unless we stored pane IDs in registry (which involves state).
        # We will split a NEW pane for each active module.
        
        pane = window.split(attach=False)
        window.select_layout("tiled")
        
        # Set Pane Title for Identity
        try:
            pane.cmd('select-pane', '-T', name)
        except Exception as e:
            print(f"⚠️ Failed to set pane title: {e}")
        
        # Setup environment
        # Use absolute pathing
        # Custom or Default Command
        custom_cmd = config.get("command")
        
        # STRICT ISOLATION: Use the venv inside the module directory
        # User Requirement: "setiap sub fungsi pakai venv sendiri sendiri"
        # We assume Linux/WSL paths based on user's environment (bin/python3)
        venv_python = os.path.join(module_path, "venv", "bin", "python3")
        
        # Verify if venv exists, otherwise warn (but try to proceed or fail)
        if not os.path.exists(venv_python):
             print(f"⚠️  WARNING: Local venv not found for {name} at {venv_python}")
             print(f"    Falling back to system python, but this may fail dependencies.")
             python_exe = "python3" # Fallback
        else:
             python_exe = venv_python
        
        if custom_cmd:
            # If custom command (e.g. "streamlit run dashboard.py")
            if custom_cmd.startswith("streamlit"):
                # Run streamlit module using the ISOLATED python
                cmd = f"cd {module_path} && {python_exe} -m {custom_cmd}"
            else:
                # For raw commands, we preface with the venv python if it looks like a python script
                # But if it's a shell command, we trust the custom_cmd.
                # Simplest assumption: custom_cmd is just the script name or args
                cmd = f"cd {module_path} && {python_exe} {custom_cmd}"
        else:
             # Default: python [module]_main.py
             script = f"{name}_main.py"
             cmd = f"cd {module_path} && {python_exe} -u {script}"
             
        pane.send_keys(cmd, enter=True)
        
        time.sleep(0.5) # Give tmux a moment to layout
        
    print("✅ All systems ignited.")
    
    root_python = "./venv/bin/python3"  # Relative to root

    print("👁️ Launching Log Watcher (Background)...")
    log_watcher_path = os.path.abspath(os.path.join(os.getcwd(), "tools", "log_watcher.py"))
    watcher_cmd = f"nohup {root_python} -u {log_watcher_path} > log_watcher.log 2>&1 &"
    boot_pane.send_keys(watcher_cmd, enter=True)
    time.sleep(1)

    print("🖥️ Launching Genesis Dashboard (Background)...")
    dashboard_path = os.path.abspath(os.path.join(os.getcwd(), "tools", "dashboard.py"))
    
    dashboard_cmd = f"nohup {root_python} -m streamlit run {dashboard_path} > dashboard.log 2>&1 &"
    boot_pane.send_keys(dashboard_cmd, enter=True)
    time.sleep(2) # Wait for startup

    print("👑 Handing over control to Mother Gaia...")
    
    # We send the command to OURSELVES (Boot Pane) to be executed after we exit
    boot_pane.send_keys("clear", enter=True)
    # Mother Gaia also uses her own 'root' venv (where this script is running from usually)
    boot_pane.send_keys("./venv/bin/python3 -u mother_gaia.py", enter=True)

if __name__ == "__main__":
    main()
