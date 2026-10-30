# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 NetworkHub contributors
"""NetworkHub desktop interface for Windows multi-connection routing."""
from pathlib import Path
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import psutil
from filelock import FileLock, Timeout
from network_engine import BASE, DATA, Engine, elevated, discover_networks

BG, PANEL, TEXT, MUTED, BLUE = "#101722", "#1b2736", "#eef4ff", "#9fb1c9", "#62bdff"
LABELS = {}
MODES = {"All-app mode (administrator)":"tun", "Browsers and proxy-aware apps":"browser",
         "Manual HTTP / SOCKS proxy":"proxy"}


class NetworkHub:
    def __init__(self, root, self_test=False):
        self.root, self.self_test = root, self_test
        self.engine = Engine()
        self.events = queue.Queue()
        self.stop_poll = threading.Event()
        self.busy = False
        self.interfaces = {}
        self.cards = {}
        self.choices = {}
        self.settings_path = DATA/"app-settings.json"
        self.first_discovery = not self.settings_path.exists()
        self.settings = {"interfaces":[]}
        try:
            self.settings.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        root.title("NetworkHub")
        root.geometry("1000x820")
        root.minsize(900, 760)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI",11), padding=(20,10))
        style.configure("TButton", font=("Segoe UI",10), padding=(14,9))
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=29, font=("Segoe UI",10))
        style.configure("Treeview.Heading", font=("Segoe UI",10,"bold"))
        style.configure("Hub.Horizontal.TProgressbar", background=BLUE, troughcolor=PANEL,
                        bordercolor=BG, lightcolor=BLUE, darkcolor=BLUE)
        header = tk.Frame(root,bg=BG,padx=28,pady=20)
        header.pack(fill="x")
        self.label(header,"NetworkHub",26,True).pack(side="left")
        self.label(header,"MULTIPLE CONNECTIONS · ONE CONTROL PANEL",10,color=MUTED).pack(side="right",pady=9)
        tabs = ttk.Notebook(root)
        tabs.pack(fill="both",expand=True,padx=24,pady=(0,14))
        connections = tk.Frame(tabs,bg=BG,padx=12,pady=18)
        programs = tk.Frame(tabs,bg=BG,padx=12,pady=18)
        downloads = tk.Frame(tabs,bg=BG,padx=12,pady=18)
        tabs.add(connections,text="Connections")
        tabs.add(programs,text="Programs")
        tabs.add(downloads,text="How it works")
        self.total_speed = tk.StringVar(value="0.0 Mbps")
        self.label(connections,"NETWORK ACTIVITY",10,color=MUTED).pack(anchor="w")
        self.label(connections,self.total_speed,36,True).pack(anchor="w",pady=(4,2))
        self.label(connections,"Combined adapter activity across your selected connections",10,color=MUTED).pack(anchor="w",pady=(0,14))
        self.network_frames = tk.Frame(connections,bg=BG)
        self.network_frames.pack(fill="x")
        for name in self.settings["interfaces"]:
            self.add_card(name)
        control = tk.Frame(connections,bg=PANEL,padx=16,pady=14)
        control.pack(fill="x",pady=(12,0))
        self.label(control,"Route other programs",13,True,bg=PANEL).pack(anchor="w")
        self.label(control,"Separate connections can use different networks. One connection uses one network.",
                   10,color=MUTED,bg=PANEL).pack(anchor="w",pady=(4,10))
        self.mode = tk.StringVar(value="Manual HTTP / SOCKS proxy")
        self.mode_pick = ttk.Combobox(control,textvariable=self.mode,values=list(MODES),state="readonly",width=35)
        self.mode_pick.pack(side="left")
        self.enable = ttk.Button(control,text="Enable routing",command=self.start)
        self.enable.pack(side="left",padx=8)
        self.disable = ttk.Button(control,text="Stop routing",command=self.stop)
        self.disable.pack(side="left")
        footer = tk.Frame(connections,bg=BG)
        footer.pack(fill="x",pady=12)
        ttk.Button(footer,text="Refresh connections",command=self.refresh).pack(side="left")
        ttk.Button(footer,text="Recover networking",command=self.stop).pack(side="left",padx=8)
        self.routing_state = tk.StringVar(value="Routing is off")
        self.label(footer,self.routing_state,11,color=BLUE).pack(side="right")

        self.label(programs,"Active routed connections",20,True).pack(anchor="w")
        self.label(programs,"Programs appear here after routing is enabled. Local-network traffic stays direct.",
                   11,color=MUTED).pack(anchor="w",pady=(5,16))
        columns=("program","destination","network","download")
        self.tree = ttk.Treeview(programs,columns=columns,show="headings")
        for name,title,width in (("program","Program",160),("destination","Destination",290),
                                 ("network","Connection",200),("download","Received",110)):
            self.tree.heading(name,text=title)
            self.tree.column(name,width=width,minwidth=90)
        self.tree.pack(fill="both",expand=True)
        self.label(programs,"Manual proxy address: 127.0.0.1:10890  ·  HTTP and SOCKS5",11,color=MUTED).pack(anchor="w",pady=14)

        self.label(downloads,"How NetworkHub works",24,True).pack(anchor="w")
        explanation = (
            "1. Windows reports your connected network adapters.\n\n"
            "2. NetworkHub configures Mihomo with a direct route for each selected adapter.\n\n"
            "3. Each new connection is assigned to an available route using round-robin balancing.\n\n"
            "4. Manual proxy, Windows user proxy, or administrator TUN mode sends traffic to the engine.\n\n"
            "5. Stop routing restores the Windows proxy settings managed by NetworkHub.\n\n"
            "One connection uses one network. Multiple connections can use several networks together. "
            "Combining one connection requires a remote bonding server.\n\n"
            "This version supports IPv4. All-app TUN mode is experimental; some applications may bypass it. "
            "Adapter activity includes other software. Independent internet sources give the greatest benefit."
        )
        self.label(downloads,explanation,12,color=MUTED,wraplength=860).pack(anchor="w",pady=20)
        bottom = tk.Frame(root,bg=BG,padx=28,pady=12)
        bottom.pack(fill="x")
        self.note = tk.StringVar(value="Select your networks, then enable a routing mode. Full single-stream bonding needs a remote server.")
        self.label(bottom,self.note,10,color=MUTED,wraplength=935).pack(anchor="w")
        root.protocol("WM_DELETE_WINDOW",self.close)
        root.report_callback_exception=lambda kind,error,trace:messagebox.showerror("NetworkHub",str(error),parent=root)
        if not self_test:
            self.refresh()
            threading.Thread(target=self.poll,daemon=True).start()
        self.tick()

    def label(self,parent,value,size,bold=False,color=TEXT,bg=BG,**kwargs):
        key="textvariable" if isinstance(value,tk.Variable) else "text"
        return tk.Label(parent,**{key:value},bg=bg,fg=color,font=("Segoe UI",size,"bold" if bold else "normal"),
                        anchor="w",justify="left",**kwargs)

    def add_card(self,name):
        if name in self.cards:
            return
        frame=tk.Frame(self.network_frames,bg=PANEL,padx=16,pady=10)
        frame.pack(fill="x",pady=(0,7))
        selected=tk.BooleanVar(value=name in self.settings["interfaces"])
        self.choices[name]=selected
        tk.Checkbutton(frame,text=LABELS.get(name,name),variable=selected,command=self.save,
            bg=PANEL,fg=TEXT,selectcolor=BG,activebackground=PANEL,activeforeground=TEXT,
            font=("Segoe UI",12,"bold"),highlightthickness=0,bd=0).grid(row=0,column=0,sticky="w")
        speed=tk.StringVar(value="— Mbps")
        state=tk.StringVar(value="Checking…")
        self.label(frame,speed,19,True,bg=PANEL).grid(row=0,column=1,sticky="e")
        self.label(frame,state,10,color=MUTED,bg=PANEL).grid(row=1,column=0,columnspan=2,sticky="w",pady=(3,0))
        frame.columnconfigure(0,weight=1)
        self.cards[name]=(speed,state)

    def save(self):
        self.settings["interfaces"]=[name for name,value in self.choices.items() if value.get()]
        self.settings_path.write_text(json.dumps(self.settings,indent=2),encoding="utf-8")
        self.note.set("Connection selection saved. Restart routing to apply it to other programs.")

    def refresh(self):
        def task():
            try:
                self.events.put(("networks",discover_networks()))
            except Exception as error:
                self.events.put(("error",str(error)))
        threading.Thread(target=task,daemon=True).start()

    def run_task(self,action,success):
        if self.busy:
            return
        self.busy=True
        self.enable["state"]=self.disable["state"]="disabled"
        def task():
            try:
                action()
                self.events.put(("complete",success))
            except Exception as error:
                self.events.put(("error",str(error)))
        threading.Thread(target=task,daemon=True).start()

    def start(self):
        names=[name for name,value in self.choices.items() if value.get()]
        if not names:
            self.note.set("Select at least one connection.")
            return
        self.save()
        mode=MODES[self.mode.get()]
        if mode=="tun" and not elevated():
            self.note.set("Windows will ask for administrator access to create the virtual network adapter.")
            self.engine.stop()
            program=sys.executable
            arguments=["--enable-tun"]
            if not getattr(sys,"frozen",False):
                arguments.insert(0,str(BASE/"network_hub.py"))
            result=ctypes.windll.shell32.ShellExecuteW(None,"runas",program,subprocess.list2cmdline(arguments),str(BASE),1)
            if result<=32:
                raise RuntimeError("Administrator access was not granted. Routing remains off.")
            self.stop_poll.set()
            self.root.destroy()
            return
        self.note.set("Starting routing…")
        self.run_task(lambda:self.engine.start(names,mode),"Routing enabled. Existing app connections may need to reconnect.")

    def stop(self):
        self.run_task(self.engine.stop,"Routing stopped. Previous Windows proxy settings restored when managed by NetworkHub.")

    def poll(self):
        last=psutil.net_io_counters(pernic=True)
        previous=time.monotonic()
        next_refresh=previous+30
        while not self.stop_poll.wait(2):
            now=time.monotonic()
            if now>=next_refresh:
                self.refresh()
                next_refresh=now+30
            current=psutil.net_io_counters(pernic=True)
            speeds={name:max(0,(value.bytes_recv-last[name].bytes_recv)*8/(now-previous)/1e6)
                    for name,value in current.items() if name in last}
            last,previous=current,now
            self.events.put(("activity",speeds))
            self.events.put(("engine",self.engine.summary()))

    def tick(self):
        while not self.events.empty():
            kind,value=self.events.get_nowait()
            if kind=="networks":
                self.interfaces={network.name:network for network in value}
                if self.first_discovery:
                    self.settings["interfaces"] = list(self.interfaces)
                    self.first_discovery = False
                for name in self.interfaces:
                    self.add_card(name)
                for name,(_,state) in self.cards.items():
                    state.set("Connected" if name in self.interfaces else "Disconnected")
            elif kind=="activity":
                for name,(speed,_) in self.cards.items():
                    speed.set(f"{value.get(name,0):.1f} Mbps")
                total=sum(value.get(name,0) for name,selected in self.choices.items() if selected.get())
                self.total_speed.set(f"{total:.1f} Mbps  /  {total/8:.2f} MB/s")
            elif kind=="engine":
                self.routing_state.set({"off":"Routing is off","proxy":"Manual proxy is active",
                    "browser":"Browser routing is active","tun":"All-app routing is active"}.get(value["mode"],value["mode"]))
                self.tree.delete(*self.tree.get_children())
                for connection in value["connections"][:100]:
                    metadata=connection.get("metadata",{})
                    network=next((name.replace("Link · ","") for name in connection.get("chains",[]) if name.startswith("Link · ")),"Direct")
                    self.tree.insert("","end",values=(metadata.get("process") or "Unknown",
                        metadata.get("host") or metadata.get("destinationIP"),network,f"{connection.get('download',0)/1e6:.1f} MB"))
            elif kind in ("complete","error"):
                self.busy=False
                self.enable["state"]=self.disable["state"]="normal"
                self.note.set(value)
                if kind=="error":
                    messagebox.showerror("NetworkHub",value,parent=self.root)
        self.root.after(500,self.tick)

    def close(self):
        if self.busy:
            self.note.set("Wait for the current routing change to finish, then close the app.")
            return
        try:
            self.engine.stop()
        except Exception as error:
            messagebox.showerror("NetworkHub",f"Routing could not be stopped: {error}",parent=self.root)
            return
        self.stop_poll.set()
        self.root.destroy()


def main():
    DATA.mkdir(parents=True,exist_ok=True)
    lock=FileLock(str(DATA/"desktop.lock"))
    try:
        lock.acquire(timeout=12 if "--enable-tun" in sys.argv else 0)
    except Timeout:
        root=tk.Tk()
        root.withdraw()
        messagebox.showinfo("NetworkHub","NetworkHub is already open.")
        root.destroy()
        return
    try:
        root=tk.Tk()
        app=NetworkHub(root,self_test="--self-test" in sys.argv)
        if "--self-test" in sys.argv:
            root.update_idletasks()
            result={"width":root.winfo_width(),"height":root.winfo_height(),"connection_cards":len(app.cards),
                    "frozen":bool(getattr(sys,"frozen",False)),"core_present":app.engine.core.exists()}
            (DATA/"ui-self-test.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
            print("NetworkHub UI loaded",flush=True)
            root.after(100,root.destroy)
        elif "--enable-tun" in sys.argv:
            root.after(600,app.start)
        root.mainloop()
    finally:
        lock.release()


if __name__=="__main__":
    main()
