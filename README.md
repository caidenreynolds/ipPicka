# ipPicka

A Tkinter app for organizing and applying shared IPv4 profiles, primarily on
Windows 10/11. Run with `python3 ip_picka.py`. Changing adapter settings on
Windows requires launching the app as Administrator.

Load JSON or Create a file at the top of the collapsible 300-pixel left menu.
Select a client to add a site, or a site/subsite to add a subsite or profile.
Sites and subsites can contain both profiles and more subsites. Use the tree's
expand controls to browse; select a profile to view its settings.

Add and delete buttons appear in pairs. Delete is enabled only for the selected
object type. Deleting a client, site, or subsite asks for confirmation and removes
all of its descendant sites, subsites, and profiles from the JSON file. Cancel
preserves the branch; a save failure restores the branch in memory.

Use Clear Selection (or Escape in the tree) to enable + Client. Select a client
for + Site, or a site/subsite for + Subsite. + Subsite is disabled on profiles.
+ Profile adds under the selected site/subsite, or beside a selected profile.

Fields start disabled. Click Edit to enable them, then Load My Interfaces to
retrieve local adapter names (including disconnected adapters on Windows).
Typing in Interface filters the dropdown; manual names are also supported.
Save writes changes to the JSON file. Cancel Edits restores the saved values.
Switch to DHCP and Set IP Address are available when viewing a saved profile.
Unsaved edits prompt before switching profiles, loading files, or closing.

The last successfully loaded or created JSON file reopens next launch. Its path
is stored in `%APPDATA%\ipPicka\settings.json` on Windows, or
`~/.config/ipPicka/settings.json` elsewhere. The JSON file itself remains in its
original location. Unreadable or incompatible files produce an error dialog.

## JSON format

See `profiles.example.json` for multiple profiles and nested subsites.

```json
{
  "version": 2,
  "clients": [
    {
      "name": "Example Client",
      "sites": [
        {
          "name": "Main Site",
          "subsites": [],
          "profiles": [
            {
              "name": "PLC connection",
              "interface": "Ethernet",
              "ipv4": "192.168.0.244",
              "subnet_mask": "255.255.255.0",
              "gateway": ""
            }
          ]
        }
      ]
    }
  ]
}
```

Every subsite uses the same `name`, `subsites`, and `profiles` structure as a
site. Empty child lists may be omitted. Profile names must be unique within
their site/subsite when saving edits. Gateway may be empty on Windows.
Interface names must match the local operating system's adapter names.

Legacy version 1 flat files and profile arrays open under Imported profiles →
Default site; the next save writes version 2. Unsupported versions and invalid
profile values are rejected without replacing the currently loaded file.

Network commands follow the host operating system: Windows 10/11 both use
`netsh interface ipv4 set address`; macOS uses `networksetup -setmanual` and
`networksetup -setdhcp`. A blank gateway uses `0.0.0.0` when applying on macOS;
Windows uses `none` to configure no gateway. The saved gateway stays blank. Changing settings
requires sufficient administrator privileges. Command-dispatch tests mock
execution and do not change network settings.

## Rebuilding the applications

Install Python 3 with Tkinter on the computer doing the build. Each script
creates/reuses `.venv-build`, installs PyInstaller, runs the tests, and rebuilds
from the current source. Internet access is needed to install missing build
dependencies. Close the previous app before rebuilding.

On macOS, double-click `build_macos.command`, or run:

```bash
./build_macos.command
```

The result is `dist/ipPicka.app`. Open it in Finder or copy it into Applications.
The app requests macOS administrator authorization when Set IP Address or
Switch to DHCP is used. Viewing profiles and editing JSON need no elevation.
Cancellation leaves the network command unexecuted. No password is stored by
ipPicka. Builds use the current Mac's architecture. Distributing to other Macs
may require Developer ID signing and notarization; these local scripts do not
supply a signing identity or notarize the application.

On Windows 10/11, double-click `build_windows.bat`, or run in Command Prompt:

```bat
build_windows.bat
```

The result is the standalone `dist\ipPicka.exe`. It includes a Windows manifest
that requests administrator privileges when launched; users approve the UAC
prompt before the app opens. The build script itself needs no administrator
rights. Python is needed for building, but not for running the packaged app.

Build each application on its target OS. Existing generated output is replaced
on each build; JSON profiles outside `build` and `dist` are preserved.

To run checks without building, use `python3 -m unittest -v` (or
`py -3 -m unittest -v` on Windows).
