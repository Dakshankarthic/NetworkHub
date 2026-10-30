# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 NetworkHub contributors
"""Local multi-WAN controller. Connection balancing is not packet bonding."""
from pathlib import Path
import ctypes
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import winreg

import psutil
import requests

from network_routes import discover_networks

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA = Path(os.environ.get("NETWORKHUB_DATA_DIR") or (Path(os.environ.get("LOCALAPPDATA", Path.home()/"AppData"/"Local"))/"NetworkHub"))
PROXY_PORT, API_PORT = 10890, 19090
PROXY_ADDRESS = f"http=127.0.0.1:{PROXY_PORT};https=127.0.0.1:{PROXY_PORT}"
PRIVATE_ROUTES = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"]


def elevated():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


class WindowsProxy:
    path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    names = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")
    backup_path = DATA / "previous-proxy.json"

    def current(self):
        values = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.path) as key:
            for name in self.names:
                try:
                    value, kind = winreg.QueryValueEx(key, name)
                    values[name] = {"value":value, "kind":kind}
                except FileNotFoundError:
                    values[name] = None
        return values

    def enabled(self):
        values = self.current()
        return bool(values["ProxyEnable"] and values["ProxyEnable"]["value"] and
                    values["ProxyServer"] and values["ProxyServer"]["value"] == PROXY_ADDRESS)

    def notify(self):
        ctypes.windll.wininet.InternetSetOptionW(None, 39, None, 0)
        ctypes.windll.wininet.InternetSetOptionW(None, 37, None, 0)

    def enable(self):
        if not self.backup_path.exists():
            self.backup_path.write_text(json.dumps(self.current(), indent=2), encoding="utf-8")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, PROXY_ADDRESS)
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>;127.*;10.*;192.168.*;172.16.*;172.17.*;172.18.*;172.19.*;172.2?.*;172.30.*;172.31.*")
            try:
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                pass
        self.notify()

    def restore(self):
        if not self.backup_path.exists():
            return
        if not self.enabled():
            return  # Preserve changes made independently in Windows settings.
        values = json.loads(self.backup_path.read_text(encoding="utf-8"))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.path, 0, winreg.KEY_SET_VALUE) as key:
            for name, record in values.items():
                if record is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, name, 0, record["kind"], record["value"])
        self.notify()
        self.backup_path.unlink()


class Engine:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.core = BASE / "bin" / "mihomo.exe"
        self.config_path = DATA / "config.yaml"
        self.state_path = DATA / "runtime.json"
        self.secret_path = DATA / "controller-token.txt"
        if not self.secret_path.exists():
            self.secret_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        self.secret = self.secret_path.read_text(encoding="utf-8").strip()
        self.http = requests.Session()
        self.http.trust_env = False
        self.proxy = WindowsProxy()

    def api(self, path, method="GET", **kwargs):
        response = self.http.request(method, f"http://127.0.0.1:{API_PORT}{path}",
            headers={"Authorization":"Bearer "+self.secret}, timeout=kwargs.pop("timeout", 3), **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    def running(self):
        try:
            return bool(self.api("/version").get("version"))
        except (requests.RequestException, ValueError):
            return False

    def configuration(self, names, tun=False):
        networks = [network for network in discover_networks() if network.name in names]
        if not networks:
            raise RuntimeError("Connect at least one selected network first.")
        labels = {network.name:"Link · "+network.name for network in networks}
        config = {
            "mixed-port":PROXY_PORT, "allow-lan":False, "bind-address":"127.0.0.1",
            "external-controller":f"127.0.0.1:{API_PORT}", "secret":self.secret,
            "mode":"rule", "log-level":"info", "ipv6":False,
            "find-process-mode":"always", "interface-name":networks[0].name,
            "profile":{"store-selected":False},
            "proxies":[{"name":labels[network.name], "type":"direct", "udp":True,
                        "ip-version":"ipv4", "interface-name":network.name} for network in networks],
            "proxy-groups":[{"name":"All connections", "type":"load-balance",
                "strategy":"round-robin", "proxies":list(labels.values()),
                "url":"https://www.gstatic.com/generate_204", "interval":30, "lazy":False}],
            "rules":["PROCESS-NAME,mihomo.exe,DIRECT"]+
                [f"IP-CIDR,{cidr},DIRECT,no-resolve" for cidr in PRIVATE_ROUTES]+["MATCH,All connections"],
            "tun":{"enable":tun, "device":"NetworkHub", "stack":"gvisor", "auto-route":True,
                "auto-detect-interface":False, "strict-route":False, "mtu":1500,
                "dns-hijack":["any:53"], "route-exclude-address":PRIVATE_ROUTES},
            "dns":{"enable":True, "listen":"127.0.0.1:11053", "ipv6":False,
                "enhanced-mode":"redir-host", "default-nameserver":["1.1.1.1","8.8.8.8"],
                "nameserver":["https://1.1.1.1/dns-query","https://dns.google/dns-query"]},
        }
        return config

    def validate(self, config):
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        result = subprocess.run([str(self.core), "-t", "-d", str(DATA), "-f", str(self.config_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Routing configuration failed validation: "+result.stdout[-1200:]+result.stderr[-1200:])

    def start(self, names, mode="proxy"):
        if mode == "tun" and not elevated():
            raise PermissionError("All-app mode needs Windows administrator access.")
        config = self.configuration(names, tun=mode == "tun")
        if self.running():
            self.api("/configs?force=true", method="PUT", json={"payload":json.dumps(config)}, timeout=20)
        else:
            self.validate(config)
            with (DATA/"engine.log").open("a", encoding="utf-8") as log:
                process = subprocess.Popen([str(self.core), "-d", str(DATA), "-f", str(self.config_path)],
                    cwd=str(self.core.parent), stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            self.state_path.write_text(json.dumps({"pid":process.pid, "core":str(self.core)}, indent=2), encoding="utf-8")
            for _ in range(50):
                if self.running():
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"Routing engine stopped. Check {DATA / 'engine.log'}.")
                time.sleep(0.2)
            else:
                process.terminate()
                raise RuntimeError("Routing engine did not start in time.")
        actual = self.api("/configs")
        if mode == "tun" and not actual.get("tun", {}).get("enable"):
            self.stop()
            raise RuntimeError("Windows did not enable the virtual adapter. Check engine.log.")
        if mode == "tun":
            for _ in range(40):
                adapter = psutil.net_if_stats().get("NetworkHub")
                if adapter is not None and adapter.isup:
                    break
                time.sleep(0.25)
            else:
                self.stop()
                raise RuntimeError("The NetworkHub virtual adapter did not become active. Check engine.log.")
        if mode == "browser":
            self.proxy.enable()
        elif self.proxy.enabled():
            self.proxy.restore()
        config["secret"] = self.secret
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        state = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}
        state.update(mode=mode, interfaces=names)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def stop(self):
        errors = []
        try:
            if self.running():
                config = json.loads(self.config_path.read_text(encoding="utf-8"))
                config["tun"]["enable"] = False
                self.api("/configs?force=true", method="PUT", json={"payload":json.dumps(config)}, timeout=20)
                self.api("/connections", method="DELETE")
        except (OSError, ValueError, requests.RequestException) as error:
            errors.append(error)
        try:
            self.proxy.restore()
        except (OSError, ValueError) as error:
            errors.append(error)
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            try:
                process = psutil.Process(state["pid"])
                if Path(process.exe()).resolve() == self.core.resolve():
                    process.terminate()
                    process.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired, KeyError):
                pass
            state["mode"] = "off"
            self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        if self.running() and self.api("/configs").get("tun", {}).get("enable"):
            raise RuntimeError("All-app routing is still active. Open NetworkHub as administrator and choose Recover networking.")
        if errors and self.proxy.enabled():
            raise RuntimeError("Windows proxy recovery did not finish. Choose Recover networking again.")

    def summary(self):
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            active = self.api("/connections")
            return {"mode":state.get("mode", "proxy"), "connections":active.get("connections") or [],
                    "download_total":active.get("downloadTotal", 0), "upload_total":active.get("uploadTotal", 0)}
        except (OSError, ValueError, requests.RequestException):
            return {"mode":"off", "connections":[], "download_total":0, "upload_total":0}
