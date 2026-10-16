import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import subprocess
import shlex

from ip_picka import (
    network_command_for_execution,
    IpPickaApp,
    IpOctetInput,
    normalize_config,
    empty_config,
    validate_subnet,
    discover_network_interfaces,
    parse_linux_interfaces,
    parse_macos_interfaces,
    parse_windows_interfaces,
)


class InterfaceParserTests(unittest.TestCase):
    def test_parses_windows_adapter_names(self):
        output = "\nEthernet\nWi-Fi\nvEthernet (Default Switch)\n"
        self.assertEqual(
            parse_windows_interfaces(output),
            ["Ethernet", "Wi-Fi", "vEthernet (Default Switch)"],
        )

    def test_parses_macos_services_and_removes_disabled_marker(self):
        output = (
            "An asterisk (*) denotes that a network service is disabled.\n"
            "Wi-Fi\n"
            "*Thunderbolt Bridge\n"
        )
        self.assertEqual(
            parse_macos_interfaces(output),
            ["Wi-Fi", "Thunderbolt Bridge"],
        )

    def test_ignores_macos_authorization_error(self):
        self.assertEqual(
            parse_macos_interfaces("AuthorizationCreate() failed: -60008\n"),
            [],
        )

    def test_parses_linux_interface_names(self):
        output = "1: lo: <LOOPBACK>\n2: eth0@if3: <BROADCAST>\n"
        self.assertEqual(parse_linux_interfaces(output), ["lo", "eth0"])


class ConfigTests(unittest.TestCase):
    def profile(self):
        return {"name": "PLC", "interface": "Ethernet 2", "ipv4": "10.0.0.2",
                "subnet_mask": "255.255.255.0", "gateway": ""}

    def test_recursive_sites_and_profiles_round_trip(self):
        leaf = {"name": "Cabinet", "profiles": [self.profile()], "subsites": []}
        for depth in range(20):
            leaf = {"name": str(depth), "profiles": [self.profile()], "subsites": [leaf]}
        config = {"version": 2, "clients": [{"name": "Client", "sites": [leaf]}]}
        self.assertEqual(normalize_config(config), config)

    def test_empty_config_is_valid(self):
        self.assertEqual(normalize_config(empty_config()), empty_config())

    def test_legacy_profiles_migrate(self):
        for config in ([self.profile()], {"version": 1, "profiles": [self.profile()]}):
            result = normalize_config(config)
            self.assertEqual(result["version"], 2)
            self.assertEqual(result["clients"][0]["sites"][0]["profiles"], [self.profile()])

    def test_rejects_incompatible_configs(self):
        for config in ({}, {"version": 3, "clients": []}, {"clients": {}},
                       {"clients": [None]}, {"clients": [{"name": "C", "sites": "bad"}]},
                       {"version": 2, "profiles": []}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                normalize_config(config)

    def test_rejects_invalid_nested_profile(self):
        for key, value in (("ipv4", "300.1.1.1"), ("subnet_mask", "255.0.255.0"),
                           ("gateway", "bad"), ("interface", ""), ("name", None)):
            profile = self.profile()
            profile[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                normalize_config({"clients": [{"name": "C", "sites": [
                    {"name": "S", "subsites": [{"name": "Nested", "profiles": [profile]}]}]}]})

    def test_subnet_rejects_hostmask(self):
        with self.assertRaises(ValueError):
            validate_subnet("0.0.0.255")

    @patch("ip_picka.subprocess.run")
    def test_windows_discovery_preserves_spaces_and_deduplicates(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "Ethernet 2\nWi-Fi\nEthernet 2\n", "")
        self.assertEqual(discover_network_interfaces("Windows"), ["Ethernet 2", "Wi-Fi"])
        self.assertEqual(run.call_args.args[0][0], "powershell.exe")

    @patch("ip_picka.subprocess.run")
    def test_discovery_failure_is_reported(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "Access denied")
        with self.assertRaisesRegex(RuntimeError, "Access denied"):
            discover_network_interfaces("Windows")


class ProfileInteractionTests(unittest.TestCase):
    def deletion_app(self):
        profile = {"name": "PLC"}
        owner = {"profiles": [profile]}
        app = SimpleNamespace(tree=Mock(), nodes={"p": ("profile", profile, owner)},
                              selected_profile=profile, new_profile_mode=False,
                              save_config=Mock(return_value=True), set_form=Mock(),
                              refresh_tree=Mock(), write_output=Mock())
        app.tree.selection.return_value = ("p",)
        return app, profile, owner

    @patch("ip_picka.DeleteProfileDialog")
    def test_delete_cancel_preserves_profile(self, dialog):
        app, profile, owner = self.deletion_app()
        dialog.return_value.result = False
        IpPickaApp.delete_node(app, "profile")
        self.assertEqual(owner["profiles"], [profile])
        app.save_config.assert_not_called()

    @patch("ip_picka.DeleteProfileDialog")
    def test_delete_persists_and_clears_selection(self, dialog):
        app, _, owner = self.deletion_app()
        dialog.return_value.result = True
        IpPickaApp.delete_node(app, "profile")
        self.assertEqual(owner["profiles"], [])
        self.assertIsNone(app.selected_profile)
        app.refresh_tree.assert_called_once_with(owner)

    @patch("ip_picka.DeleteProfileDialog")
    def test_failed_delete_save_restores_original_position(self, dialog):
        app, profile, owner = self.deletion_app()
        other = {"name": "Other"}
        owner["profiles"].append(other)
        app.save_config.return_value = False
        dialog.return_value.result = True
        IpPickaApp.delete_node(app, "profile")
        self.assertEqual(owner["profiles"], [profile, other])
        self.assertIs(app.selected_profile, profile)
        app.refresh_tree.assert_not_called()

    def test_profile_path_includes_all_parents(self):
        owner = {"name": "Subsite A", "subsites": []}
        app = SimpleNamespace(selected_profile={"name": "PLC"}, new_profile_mode=False,
                              profile_parent=owner, config_data={"clients": [
                                  {"name": "Client", "sites": [{"name": "Site", "subsites": [owner]}]}]})
        self.assertEqual(IpPickaApp.profile_location(app), "Client/Site/Subsite A")

    def test_octet_advance_only_for_third_digit(self):
        entry = Mock()
        entry.get.return_value = "192"
        widget = SimpleNamespace(entries=[entry], focus_get=lambda: entry, _advance=Mock())
        change = Mock()
        IpOctetInput._on_key_release(widget, SimpleNamespace(char="2"), 0, change)
        widget._advance.assert_called_once_with(0)
        for char, value in (("", "192"), ("1", "19"), ("\b", "192")):
            widget._advance.reset_mock()
            entry.get.return_value = value
            IpOctetInput._on_key_release(widget, SimpleNamespace(char=char), 0, change)
            widget._advance.assert_not_called()

    def test_period_advances_without_inserting_text(self):
        entry = Mock()
        entry.cget.return_value = "normal"
        widget = SimpleNamespace(entries=[entry], _advance=Mock())
        self.assertEqual(IpOctetInput._on_period(widget, 0), "break")
        widget._advance.assert_called_once_with(0)


class HierarchyActionTests(unittest.TestCase):
    def test_add_selection_rules(self):
        allowed = {None: {"client"}, "client": {"site"},
                   "site": {"subsite", "profile"}, "subsite": {"subsite", "profile"},
                   "profile": {"profile"}}
        for selection, expected in allowed.items():
            app = SimpleNamespace(config_path="config.json", tree=Mock(),
                                  nodes={"x": (selection, {}, None)})
            app.tree.selection.return_value = ("x",) if selection else ()
            for kind in ("client", "site", "subsite", "profile"):
                with self.subTest(selection=selection, kind=kind):
                    self.assertEqual(IpPickaApp.can_add_node(app, kind), kind in expected)
            app.config_path = None
            self.assertFalse(IpPickaApp.can_add_node(app, "client"))

    def test_delete_buttons_match_selection_type(self):
        for kind in (None, "client", "site", "subsite", "profile"):
            app = SimpleNamespace(config_path="config.json", tree=Mock(),
                                  nodes={"x": (kind, {}, None)}, new_profile_mode=False,
                                  add_buttons={}, delete_buttons={k: Mock() for k in
                                      ("client", "site", "subsite", "profile")})
            app.tree.selection.return_value = ("x",) if kind else ()
            IpPickaApp.update_menu_buttons(app)
            for button_kind, button in app.delete_buttons.items():
                button.configure.assert_called_with(state="normal" if button_kind == kind else "disabled")
            app.new_profile_mode = True
            IpPickaApp.update_menu_buttons(app)
            for button in app.delete_buttons.values():
                button.configure.assert_called_with(state="disabled")

    @patch("ip_picka.DeleteProfileDialog")
    def test_delete_branches_cancel_success_and_save_failure(self, dialog):
        for kind, key in (("client", "clients"), ("site", "sites"), ("subsite", "subsites")):
            for confirm, saved in ((False, True), (True, False), (True, True)):
                with self.subTest(kind=kind, confirm=confirm, saved=saved):
                    obj = {"name": "Branch", "subsites": [{"name": "Nested", "profiles": [{"name": "PLC"}]}]}
                    other = {"name": "Other"}
                    owner = {key: [obj, other]}
                    app = SimpleNamespace(tree=Mock(), nodes={"x": (kind, obj, owner)},
                                          config_data=owner, new_profile_mode=False,
                                          save_config=Mock(return_value=saved), set_form=Mock(),
                                          refresh_tree=Mock(), write_output=Mock())
                    app.tree.selection.return_value = ("x",)
                    dialog.return_value.result = confirm
                    IpPickaApp.delete_node(app, kind)
                    self.assertEqual(owner[key], [other] if confirm and saved else [obj, other])
                    dialog.assert_called_with(app, "Branch", kind)

    @patch("ip_picka.DeleteProfileDialog")
    def test_delete_wrong_kind_does_nothing(self, dialog):
        app = SimpleNamespace(tree=Mock(), nodes={"x": ("site", {}, {})}, new_profile_mode=False)
        app.tree.selection.return_value = ("x",)
        IpPickaApp.delete_node(app, "client")
        dialog.assert_not_called()


class NetworkCommandTests(unittest.TestCase):
    def app(self, gateway="10.0.0.1"):
        profile = {"name": "PLC", "interface": "Ethernet 2", "ipv4": "10.0.0.2",
                   "subnet_mask": "255.255.255.0", "gateway": gateway}
        return SimpleNamespace(validate_form_profile=lambda: profile, run_command=Mock(),
                               interface_var=SimpleNamespace(get=lambda: profile["interface"]))

    @patch("ip_picka.platform.system", return_value="Windows")
    def test_windows_10_and_11_use_netsh(self, system):
        for release in ("10", "11"):
            with self.subTest(release=release), patch("ip_picka.platform.release", return_value=release):
                app = self.app()
                IpPickaApp.apply_current_profile(app)
                app.run_command.assert_called_once_with([
                    "netsh", "interface", "ipv4", "set", "address", "name=Ethernet 2",
                    "static", "10.0.0.2", "255.255.255.0", "10.0.0.1"])
                app.run_command.reset_mock()
                IpPickaApp.switch_to_dhcp(app)
                app.run_command.assert_called_once_with([
                    "netsh", "interface", "ipv4", "set", "address", "name=Ethernet 2", "dhcp"])

    @patch("ip_picka.platform.system", return_value="Windows")
    def test_windows_blank_gateway_removes_gateway(self, system):
        app = self.app(gateway="")
        IpPickaApp.apply_current_profile(app)
        self.assertEqual(app.run_command.call_args.args[0][-1], "none")

    @patch("ip_picka.platform.system", return_value="Darwin")
    def test_macos_uses_networksetup(self, system):
        app = self.app()
        IpPickaApp.apply_current_profile(app)
        app.run_command.assert_called_once_with([
            "networksetup", "-setmanual", "Ethernet 2", "10.0.0.2", "255.255.255.0", "10.0.0.1"])
        app.run_command.reset_mock()
        IpPickaApp.switch_to_dhcp(app)
        app.run_command.assert_called_once_with(["networksetup", "-setdhcp", "Ethernet 2"])

    @patch("ip_picka.messagebox.showerror")
    @patch("ip_picka.platform.system", return_value="Darwin")
    def test_macos_blank_gateway_uses_zero_without_changing_profile(self, system, error):
        app = self.app(gateway="")
        IpPickaApp.apply_current_profile(app)
        app.run_command.assert_called_once_with([
            "networksetup", "-setmanual", "Ethernet 2", "10.0.0.2", "255.255.255.0", "0.0.0.0"])
        self.assertEqual(app.validate_form_profile()["gateway"], "")
        error.assert_not_called()

    @patch("ip_picka.messagebox.showerror")
    @patch("ip_picka.platform.system", return_value="Linux")
    def test_unsupported_system_does_not_run_commands(self, system, error):
        app = self.app()
        IpPickaApp.apply_current_profile(app)
        IpPickaApp.switch_to_dhcp(app)
        app.run_command.assert_not_called()
        self.assertEqual(error.call_count, 2)


class AuthorizationTests(unittest.TestCase):
    def test_macos_network_changes_prompt_with_safely_quoted_arguments(self):
        interface = 'Ethernet "2"; $(touch /tmp/unwanted)'
        for mode in ("-setmanual", "-setdhcp"):
            command = ["networksetup", mode, interface]
            wrapped = network_command_for_execution(command, "Darwin")
            self.assertEqual(wrapped[:2], ["/usr/bin/osascript", "-e"])
            self.assertIn("with administrator privileges", wrapped[2])
            self.assertNotIn(interface, wrapped[2])
            self.assertEqual(shlex.split(wrapped[3]), ["/usr/sbin/networksetup", mode, interface])

    def test_macos_read_only_commands_do_not_prompt(self):
        command = ["networksetup", "-getinfo", "Wi-Fi"]
        self.assertEqual(network_command_for_execution(command, "Darwin"), command)

    def test_windows_uses_executable_elevation_without_wrapping_commands(self):
        command = ["netsh", "interface", "ipv4", "set", "address", "name=Ethernet", "dhcp"]
        self.assertEqual(network_command_for_execution(command, "Windows"), command)


if __name__ == "__main__":
    unittest.main()
