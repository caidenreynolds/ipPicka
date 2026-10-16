# ipPicka

A Tkinter app for organizing and applying shared IPv4 profiles, primarily on
Windows 10/11. Run with `python3 ip_picka.py`. Changing adapter settings on
Windows requires launching the app as Administrator.

Load JSON or Create a file at the top of the collapsible 300-pixel left menu.
Select a client to add a site, or a site/subsite to add a subsite or profile.
Sites and subsites can contain both profiles and more subsites. Use the tree's
expand controls to browse; select a profile to view its settings.

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

## Validation and Windows build

Run `python3 -m unittest -v`. To produce a Windows executable, run PyInstaller
on Windows with `pyinstaller ipPicka.spec` (install PyInstaller first). Builds
are platform-specific; a macOS build cannot produce a Windows executable.
