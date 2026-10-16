import json
import os
import ipaddress
import platform
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, simpledialog, ttk


APP_TITLE = "ipPicka"
CONFIG_VERSION = 2


def empty_config():
    return {"version": CONFIG_VERSION, "clients": []}


def normalize_config(data):
    if isinstance(data, list):
        data = {"version": 1, "profiles": data}
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object.")
    version = data.get("version", 1 if "profiles" in data else CONFIG_VERSION)
    if type(version) is not int or version not in (1, CONFIG_VERSION):
        raise ValueError("Unsupported config version.")
    if "clients" not in data:
        if "profiles" not in data or version != 1:
            raise ValueError("Config must contain a 'clients' list.")
        data = {"clients": [{"name": "Imported profiles", "sites": [
            {"name": "Default site", "profiles": data["profiles"]}]}]}

    def items(obj, key):
        value = obj.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"'{key}' must be a list.")
        return value

    def name(obj):
        if not isinstance(obj, dict) or not isinstance(obj.get("name"), str) or not obj["name"].strip():
            raise ValueError("Every client, site, subsite, and profile needs a name.")
        return obj["name"].strip()

    def profile(obj):
        result = {"name": name(obj)}
        for key, alias in (("interface", "interface"), ("ipv4", "ip"),
                           ("subnet_mask", "subnet"), ("gateway", "default_gateway")):
            value = obj.get(key, obj.get(alias, ""))
            if not isinstance(value, str):
                raise ValueError(f"Profile '{result['name']}': {key} must be text.")
            result[key] = value.strip()
        if not result["interface"]:
            raise ValueError("Profile interface is required.")
        result["ipv4"] = validate_ipv4(result["ipv4"], "IPv4 address")
        result["subnet_mask"] = validate_subnet(result["subnet_mask"])
        result["gateway"] = validate_ipv4(result["gateway"], "Gateway", required=False)
        return result

    def site(obj):
        return {"name": name(obj), "subsites": [site(x) for x in items(obj, "subsites")],
                "profiles": [profile(x) for x in items(obj, "profiles")]}

    return {"version": CONFIG_VERSION, "clients": [
        {"name": name(c), "sites": [site(x) for x in items(c, "sites")]}
        for c in items(data, "clients")]}


def validate_subnet(value):
    value = validate_ipv4(value, "Subnet mask")
    try:
        ipaddress.IPv4Network("0.0.0.0/" + value)
        bits = f"{int(ipaddress.IPv4Address(value)):032b}"
        if "01" in bits:
            raise ValueError()
    except ValueError:
        raise ValueError("Subnet mask must contain contiguous network bits.") from None
    return value


def settings_path():
    base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    return base / APP_TITLE / "settings.json"


def split_ipv4(value):
    parts = str(value or "").split(".")
    if len(parts) != 4:
        return ["", "", "", ""]
    return parts


def validate_ipv4(value, label, required=True):
    value = value.strip()
    if not value and not required:
        return ""

    parts = value.split(".")
    if len(parts) != 4:
        raise ValueError(f"{label} must have four octets.")
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"{label} can only contain numbers.")
        number = int(part)
        if number < 0 or number > 255:
            raise ValueError(f"{label} octets must be between 0 and 255.")
    return ".".join(str(int(part)) for part in parts)


def parse_windows_interfaces(output):
    return [line.strip() for line in output.splitlines() if line.strip()]


def parse_macos_interfaces(output):
    interfaces = []
    for line in output.splitlines():
        name = line.strip()
        if (
            not name
            or name.startswith("An asterisk")
            or "AuthorizationCreate() failed" in name
        ):
            continue
        interfaces.append(name.removeprefix("*").strip())
    return interfaces


def parse_linux_interfaces(output):
    interfaces = []
    for line in output.splitlines():
        fields = line.split(":", maxsplit=2)
        if len(fields) < 2:
            continue
        interfaces.append(fields[1].strip().split("@", maxsplit=1)[0])
    return interfaces


def discover_network_interfaces(system=None):
    system = system or platform.system()
    if system == "Windows":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Get-NetAdapter | Sort-Object Name | Select-Object -ExpandProperty Name",
        ]
        parser = parse_windows_interfaces
    elif system == "Darwin":
        command = ["networksetup", "-listallnetworkservices"]
        parser = parse_macos_interfaces
    elif system == "Linux":
        command = ["ip", "-o", "link", "show"]
        parser = parse_linux_interfaces
    else:
        raise RuntimeError(f"Adapter discovery is not supported on {system}.")

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        error = completed.stderr.strip() or f"Command exited with code {completed.returncode}."
        raise RuntimeError(error)
    interfaces = list(dict.fromkeys(parser(completed.stdout)))
    if not interfaces:
        error = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(error or "No network interfaces were found.")
    return interfaces


class DeleteProfileDialog(simpledialog.Dialog):
    def __init__(self, parent, name):
        self.profile_name = name
        self.result = False
        super().__init__(parent, title="Delete Profile")

    def body(self, master):
        ttk.Label(master, text=f'Are you sure you want to delete "{self.profile_name}"?',
                  wraplength=400).pack(padx=12, pady=12)

    def buttonbox(self):
        buttons = ttk.Frame(self)
        buttons.pack(padx=12, pady=(0, 12), fill="x")
        cancel = ttk.Button(buttons, text="Cancel", command=self.cancel)
        cancel.pack(side="right", padx=4)
        ttk.Button(buttons, text="Delete", command=self.ok).pack(side="right", padx=4)
        self.bind("<Escape>", self.cancel)
        self.initial_focus = cancel

    def apply(self):
        self.result = True


class IpOctetInput(ttk.Frame):
    def __init__(self, master, label, on_change):
        super().__init__(master)
        self.entries = []
        ttk.Label(self, text=label, width=16).grid(row=0, column=0, sticky="w")

        validate_cmd = (self.register(self._validate_octet), "%P")
        for index in range(4):
            entry = ttk.Entry(
                self,
                width=4,
                justify="center",
                validate="key",
                validatecommand=validate_cmd,
            )
            entry.grid(row=0, column=index * 2 + 1, padx=(0, 2))
            entry.bind("<KeyRelease>", lambda event, i=index: self._on_key_release(event, i, on_change))
            entry.bind("<KeyPress-period>", lambda _event, i=index: self._on_period(i))
            entry.bind("<KeyPress-KP_Decimal>", lambda _event, i=index: self._on_period(i))
            entry.bind("<<Paste>>", lambda _event: self.after_idle(on_change))
            self.entries.append(entry)
            if index < 3:
                ttk.Label(self, text=".").grid(row=0, column=index * 2 + 2)

    def _advance(self, index):
        if index < len(self.entries) - 1:
            entry = self.entries[index + 1]
            entry.focus_set()
            entry.selection_range(0, tk.END)
            entry.icursor(tk.END)

    def _on_period(self, index):
        if str(self.entries[index].cget("state")) != "disabled":
            self._advance(index)
        return "break"

    def _on_key_release(self, event, index, on_change):
        on_change()
        if (event.char and event.char in "0123456789"
                and len(self.entries[index].get()) == 3
                and self.focus_get() is self.entries[index]):
            self._advance(index)

    def _validate_octet(self, proposed):
        return proposed == "" or (proposed.isdigit() and len(proposed) <= 3)

    def set_state(self, state):
        for entry in self.entries:
            entry.configure(state=state)

    def set_value(self, value):
        parts = split_ipv4(value)
        for entry, part in zip(self.entries, parts):
            entry.configure(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, part)

    def get_value(self):
        parts = [entry.get().strip() for entry in self.entries]
        if all(part == "" for part in parts):
            return ""
        return ".".join(parts)


class IpPickaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x650")
        self.minsize(780, 480)
        self.config_path = None
        self.config_data = empty_config()
        self.selected_profile = None
        self.profile_parent = None
        self.editing = False
        self.new_profile_mode = False
        self.loading_form = False
        self.network_interfaces = []
        self.nodes = {}
        self._build_ui()
        self.update_action_buttons()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.after_idle(self.restore_last_config)

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Show / Hide Menu", command=self.toggle_sidebar).pack(side="left")
        self.panes = ttk.Panedwindow(self, orient="horizontal")
        self.panes.pack(fill="both", expand=True)
        self.sidebar = ttk.Frame(self.panes, width=300, padding=10)
        self.panes.add(self.sidebar, weight=0)
        files = ttk.Frame(self.sidebar)
        files.pack(fill="x")
        ttk.Button(files, text="Load JSON…", command=self.open_config).pack(side="left")
        ttk.Button(files, text="Create…", command=self.create_config).pack(side="left", padx=6)
        self.path_var = tk.StringVar(value="No config selected")
        ttk.Label(self.sidebar, textvariable=self.path_var, wraplength=270).pack(fill="x", pady=8)
        tree_frame = ttk.Frame(self.sidebar)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        self.branch_font = font.nametofont("TkDefaultFont").copy()
        self.branch_font.configure(weight="bold")
        self.tree.tag_configure("branch", font=self.branch_font)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tree_frame, command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_selected)
        additions = ttk.Frame(self.sidebar)
        additions.pack(fill="x", pady=8)
        for label, kind in (("+ Client", "client"), ("+ Site", "site"),
                            ("+ Subsite", "subsite"), ("+ Profile", "profile")):
            ttk.Button(additions, text=label, command=lambda k=kind: self.add_node(k)).pack(fill="x", pady=2)
        self.delete_profile_button = ttk.Button(additions, text="- Profile", command=self.delete_profile)
        self.delete_profile_button.pack(fill="x", pady=2)
        main = ttk.Frame(self.panes, padding=16)
        self.panes.add(main, weight=1)
        self.after_idle(lambda: self.panes.sashpos(0, 300))
        form = ttk.LabelFrame(main, text="Profile Details", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.location_var = tk.StringVar()
        ttk.Label(form, textvariable=self.location_var, wraplength=550).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.name_var = tk.StringVar()
        self.interface_var = tk.StringVar()
        ttk.Label(form, text="Profile name").grid(row=1, column=0, sticky="w")
        self.name_entry = ttk.Entry(form, textvariable=self.name_var)
        self.name_entry.grid(row=1, column=1, columnspan=2, sticky="ew")
        ttk.Label(form, text="Interface").grid(row=2, column=0, sticky="w", pady=8)
        self.interface_combo = ttk.Combobox(form, textvariable=self.interface_var)
        self.interface_combo.grid(row=2, column=1, sticky="ew", pady=8)
        self.refresh_interfaces_button = ttk.Button(form, text="Load My Interfaces", command=self.refresh_network_interfaces)
        self.refresh_interfaces_button.grid(row=2, column=2, padx=(8, 0))
        self.ip_input = IpOctetInput(form, "IPv4 address", self.on_form_changed)
        self.subnet_input = IpOctetInput(form, "Subnet mask", self.on_form_changed)
        self.gateway_input = IpOctetInput(form, "Gateway (optional)", self.on_form_changed)
        for row, widget in enumerate((self.ip_input, self.subnet_input, self.gateway_input), 3):
            widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        self.name_var.trace_add("write", lambda *_: self.on_form_changed())
        self.interface_var.trace_add("write", lambda *_: self.on_form_changed())
        output_frame = ttk.LabelFrame(main, text="Command Output", padding=8)
        output_frame.pack(fill="both", expand=True, pady=12)
        ttk.Button(output_frame, text="Clear Output", command=self.clear_output).pack(
            side="bottom", anchor="e", pady=(6, 0))
        self.output = tk.Text(output_frame, height=8, wrap="word", state="disabled")
        self.output.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(output_frame, command=self.output.yview)
        scroll.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=scroll.set)
        actions = ttk.Frame(main)
        actions.pack(fill="x", side="bottom")
        ttk.Button(actions, text="Check Current IP", command=self.check_current_ip).pack(side="left")
        self.apply_button = ttk.Button(actions, text="Set IP Address", command=self.apply_current_profile)
        self.dhcp_button = ttk.Button(actions, text="Switch to DHCP", command=self.switch_to_dhcp)
        self.edit_button = ttk.Button(actions, text="Edit", command=self.edit_or_save)
        self.cancel_button = ttk.Button(actions, text="Cancel Edits", command=self.cancel_edits)
        for button in (self.apply_button, self.dhcp_button, self.edit_button):
            button.pack(side="right", padx=4)

    def toggle_sidebar(self):
        if str(self.sidebar) in self.panes.panes():
            self.panes.forget(self.sidebar)
        else:
            self.panes.insert(0, self.sidebar, weight=0)
            self.panes.sashpos(0, 300)

    def confirm_discard(self):
        return not (self.editing and (self.new_profile_mode or self.form_is_dirty())) or messagebox.askyesno(
            APP_TITLE, "Discard unsaved profile edits?")

    def close_app(self):
        if self.confirm_discard():
            self.destroy()

    def open_config(self):
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(title="Load ipPicka JSON", filetypes=[("JSON files", "*.json")])
        if path:
            self.load_config(Path(path))

    def create_config(self):
        if not self.confirm_discard():
            return
        path = filedialog.asksaveasfilename(title="Create ipPicka JSON", defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not path:
            return
        data = empty_config()
        if self.write_config(Path(path), data):
            self.config_path, self.config_data = Path(path), data
            self.after_config_loaded()

    def load_config(self, path):
        try:
            data = normalize_config(json.loads(path.read_text(encoding="utf-8-sig")))
        except (OSError, ValueError, RecursionError) as exc:
            messagebox.showerror(APP_TITLE, f"Could not load compatible JSON:\n{exc}")
            return
        self.config_path, self.config_data = path, data
        self.after_config_loaded()

    def after_config_loaded(self):
        self.path_var.set(str(self.config_path))
        self.selected_profile = None
        self.profile_parent = None
        self.editing = self.new_profile_mode = False
        self.set_form(None)
        self.refresh_tree()
        self.remember_config()
        self.write_output(f"Loaded config: {self.config_path}")

    def remember_config(self):
        try:
            path = settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"last_config": str(self.config_path.resolve())}), encoding="utf-8")
        except OSError as exc:
            self.write_output(f"Could not remember last config: {exc}")

    def restore_last_config(self):
        try:
            path = json.loads(settings_path().read_text(encoding="utf-8"))["last_config"]
        except (OSError, ValueError, KeyError, TypeError):
            return
        if isinstance(path, str):
            self.load_config(Path(path))

    def write_config(self, path, data):
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
            return True
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not save config:\n{exc}")
            return False

    def save_config(self):
        return self.write_config(self.config_path, self.config_data)

    def refresh_tree(self, target=None):
        expanded = {id(self.nodes[i][1]) for i in self.nodes if self.tree.item(i, "open")}
        self.tree.delete(*self.tree.get_children())
        self.nodes = {}
        def insert(parent, kind, obj, owner=None):
            item = self.tree.insert(parent, "end", text=obj["name"], open=id(obj) in expanded,
                                    tags=("branch",) if kind != "profile" else ())
            self.nodes[item] = (kind, obj, owner)
            for key, child_kind in (("sites", "site"), ("subsites", "subsite"), ("profiles", "profile")):
                for child in obj.get(key, []):
                    insert(item, child_kind, child, obj)
            if obj is target:
                self.tree.selection_set(item)
                self.tree.see(item)
        for client in self.config_data["clients"]:
            insert("", "client", client)

    def on_tree_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        kind, obj, owner = self.nodes[selection[0]]
        if kind == "profile" and obj is self.selected_profile:
            return
        if not self.confirm_discard():
            for item, (_, candidate, _) in self.nodes.items():
                if candidate is self.selected_profile:
                    self.tree.selection_set(item)
                    break
            return
        self.editing = self.new_profile_mode = False
        self.selected_profile = obj if kind == "profile" else None
        self.profile_parent = owner if kind == "profile" else obj
        self.set_form(self.selected_profile)

    def profile_location(self):
        def find(nodes, path):
            for node in nodes:
                current = path + [node["name"]]
                if node is self.profile_parent:
                    return current
                found = find(node.get("sites", []) + node.get("subsites", []), current)
                if found:
                    return found
            return []
        if not (self.selected_profile or self.new_profile_mode):
            return ""
        return "/".join(find(self.config_data["clients"], []))

    def set_form(self, profile):
        self.location_var.set(self.profile_location())
        profile = profile or {}
        self.loading_form = True
        self.name_var.set(profile.get("name", ""))
        self.interface_var.set(profile.get("interface", ""))
        for widget, key in ((self.ip_input, "ipv4"), (self.subnet_input, "subnet_mask"), (self.gateway_input, "gateway")):
            widget.set_value(profile.get(key, ""))
        self.loading_form = False
        self.update_action_buttons()

    def add_node(self, kind):
        if not self.config_path:
            messagebox.showinfo(APP_TITLE, "Load or create a JSON file first.")
            return
        if not self.confirm_discard():
            return
        selection = self.tree.selection()
        selected = self.nodes.get(selection[0]) if selection else None
        if kind != "client":
            if not selected:
                messagebox.showinfo(APP_TITLE, "Select a parent in the menu first.")
                return
            parent_kind, parent, owner = selected
            if parent_kind == "profile":
                parent = owner
                parent_kind = "site"
            if (kind == "site" and parent_kind != "client") or (kind in ("subsite", "profile") and parent_kind not in ("site", "subsite")):
                messagebox.showinfo(APP_TITLE, "Select a client for a site, or a site/subsite for a subsite or profile.")
                return
        if kind == "profile":
            self.profile_parent = parent
            self.selected_profile = None
            self.editing = self.new_profile_mode = True
            self.set_form(None)
            self.name_entry.focus_set()
            return
        name = simpledialog.askstring(APP_TITLE, f"New {kind} name:", parent=self)
        if not name or not name.strip():
            return
        obj = {"name": name.strip()}
        if kind == "client":
            obj["sites"] = []
            siblings = self.config_data["clients"]
        else:
            obj.update(subsites=[], profiles=[])
            siblings = parent["sites" if kind == "site" else "subsites"]
        siblings.append(obj)
        if not self.save_config():
            siblings.remove(obj)
            return
        self.cancel_edits()
        self.refresh_tree(obj)

    def delete_profile(self):
        selection = self.tree.selection()
        selected = self.nodes.get(selection[0]) if selection else None
        if not selected or selected[0] != "profile" or self.new_profile_mode:
            return
        _, profile, owner = selected
        if not DeleteProfileDialog(self, profile["name"]).result:
            return
        siblings = owner["profiles"]
        index = next(i for i, candidate in enumerate(siblings) if candidate is profile)
        siblings.pop(index)
        if not self.save_config():
            siblings.insert(index, profile)
            return
        self.selected_profile = None
        self.profile_parent = owner
        self.editing = self.new_profile_mode = False
        self.set_form(None)
        self.refresh_tree(owner)
        self.write_output(f"Deleted profile: {profile['name']}")

    def clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.configure(state="disabled")

    def refresh_network_interfaces(self):
        try:
            self.network_interfaces = discover_network_interfaces()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            messagebox.showerror(APP_TITLE, f"Could not load interfaces:\n{exc}")
            return
        self.interface_combo.configure(values=self.network_interfaces)
        self.write_output("Interfaces: " + ", ".join(self.network_interfaces))

    def filter_interfaces(self):
        query = self.interface_var.get().casefold()
        self.interface_combo.configure(values=[name for name in self.network_interfaces if query in name.casefold()])

    def on_form_changed(self):
        if not self.loading_form:
            self.filter_interfaces()
            self.update_action_buttons()

    def current_form_profile(self):
        return {"name": self.name_var.get().strip(), "interface": self.interface_var.get().strip(),
                "ipv4": self.ip_input.get_value(), "subnet_mask": self.subnet_input.get_value(),
                "gateway": self.gateway_input.get_value()}

    def form_is_dirty(self):
        return self.selected_profile is not None and self.current_form_profile() != self.selected_profile

    def update_action_buttons(self):
        self.delete_profile_button.configure(
            state="normal" if self.selected_profile and not self.new_profile_mode else "disabled")
        state = "normal" if self.editing else "disabled"
        for widget in (self.name_entry, self.interface_combo, self.refresh_interfaces_button):
            widget.configure(state=state)
        for widget in (self.ip_input, self.subnet_input, self.gateway_input):
            widget.set_state(state)
        dirty = self.new_profile_mode or self.form_is_dirty()
        self.edit_button.configure(text=("Save" if dirty else "Cancel Edits") if self.editing else "Edit",
                                   state="normal" if self.editing or self.selected_profile else "disabled")
        if self.editing and dirty:
            self.cancel_button.pack(side="right", padx=4)
        else:
            self.cancel_button.pack_forget()
        state = "normal" if self.selected_profile and not self.editing else "disabled"
        self.apply_button.configure(state=state)
        self.dhcp_button.configure(state=state)

    def cancel_edits(self):
        self.editing = self.new_profile_mode = False
        self.set_form(self.selected_profile)

    def edit_or_save(self):
        if not self.editing:
            self.editing = True
            self.update_action_buttons()
            return
        if not self.new_profile_mode and not self.form_is_dirty():
            self.cancel_edits()
            return
        try:
            profile = self.validate_form_profile()
            siblings = self.profile_parent["profiles"]
            if any(p is not self.selected_profile and p["name"].casefold() == profile["name"].casefold() for p in siblings):
                raise ValueError("A profile with that name already exists in this site/subsite.")
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if self.new_profile_mode:
            siblings.append(profile)
            if not self.save_config():
                siblings.pop()
                return
            self.selected_profile = profile
        else:
            original = self.selected_profile.copy()
            self.selected_profile.update(profile)
            if not self.save_config():
                self.selected_profile.update(original)
                return
        self.cancel_edits()
        self.refresh_tree(self.selected_profile)

    def validate_form_profile(self):
        profile = self.current_form_profile()
        if not profile["name"] or not profile["interface"]:
            raise ValueError("Profile name and interface are required.")
        profile["ipv4"] = validate_ipv4(profile["ipv4"], "IPv4 address")
        profile["subnet_mask"] = validate_subnet(profile["subnet_mask"])
        profile["gateway"] = validate_ipv4(profile["gateway"], "Gateway", required=False)
        return profile

    def apply_current_profile(self):
        try:
            profile = self.validate_form_profile()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        system = platform.system()
        if system == "Windows":
            command = [
                "netsh",
                "interface",
                "ipv4",
                "set",
                "address",
                f"name={profile['interface']}",
                "static",
                profile["ipv4"],
                profile["subnet_mask"],
            ]
            if profile["gateway"]:
                command.append(profile["gateway"])
            else:
                command.append("none")
        elif system == "Darwin":
            if not profile["gateway"]:
                messagebox.showerror(
                    APP_TITLE,
                    "macOS networksetup requires a default gateway/router.",
                )
                return
            command = [
                "networksetup",
                "-setmanual",
                profile["interface"],
                profile["ipv4"],
                profile["subnet_mask"],
                profile["gateway"],
            ]
        else:
            messagebox.showerror(APP_TITLE, f"Applying IP settings is not supported on {system}.")
            return

        self.run_command(command)

    def switch_to_dhcp(self):
        interface = self.interface_var.get().strip()
        if not interface:
            messagebox.showerror(APP_TITLE, "Network interface is required.")
            return

        system = platform.system()
        if system == "Windows":
            command = [
                "netsh",
                "interface",
                "ipv4",
                "set",
                "address",
                f"name={interface}",
                "dhcp",
            ]
        elif system == "Darwin":
            command = ["networksetup", "-setdhcp", interface]
        else:
            messagebox.showerror(
                APP_TITLE, f"Switching to DHCP is not supported on {system}."
            )
            return

        self.run_command(command)

    def check_current_ip(self):
        system = platform.system()
        if system == "Windows":
            command = ["ipconfig"]
        elif system == "Darwin":
            interface = self.interface_var.get().strip()
            if interface:
                command = ["networksetup", "-getinfo", interface]
            else:
                command = ["networksetup", "-listallnetworkservices"]
        else:
            command = ["ip", "addr"]
        self.run_command(command)

    def run_command(self, command):
        self.write_output(f"$ {' '.join(command)}")
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        output = completed.stdout.strip()
        errors = completed.stderr.strip()
        if output:
            self.write_output(output)
        if errors:
            self.write_output(errors)
        self.write_output(f"Exit code: {completed.returncode}")
        if completed.returncode != 0:
            messagebox.showwarning(
                APP_TITLE,
                "The command did not complete successfully. Administrator rights may be required.",
            )

    def write_output(self, text):
        self.output.configure(state="normal")
        self.output.insert(tk.END, text + "\n")
        self.output.see(tk.END)
        self.output.configure(state="disabled")



if __name__ == "__main__":
    app = IpPickaApp()
    app.mainloop()
