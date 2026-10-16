import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import subprocess

from ip_picka import (
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
        IpPickaApp.delete_profile(app)
        self.assertEqual(owner["profiles"], [profile])
        app.save_config.assert_not_called()

    @patch("ip_picka.DeleteProfileDialog")
    def test_delete_persists_and_clears_selection(self, dialog):
        app, _, owner = self.deletion_app()
        dialog.return_value.result = True
        IpPickaApp.delete_profile(app)
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
        IpPickaApp.delete_profile(app)
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


if __name__ == "__main__":
    unittest.main()
