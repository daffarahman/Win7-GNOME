# Win7-GNOME

A Windows 7 icon theme for GNOME, covering apps, folders, drives, and the Recycle Bin with Adwaita fallback.

The Start orb artwork is from **[b00merang / B00merang Artwork](https://github.com/B00merang-Artwork/Windows-7)**. The other icons are extracted Windows 7 resources. See [SOURCE.md](SOURCE.md) for full credits.

## Download and use

Download `Win7-GNOME.tar.xz` from the [latest release](https://github.com/daffarahman/Win7-GNOME/releases/latest).
With Adwaita installed, extract the archive and select the theme:

```sh
mkdir -p ~/.local/share/icons
tar -xJf Win7-GNOME.tar.xz -C ~/.local/share/icons
gtk-update-icon-cache -f ~/.local/share/icons/Win7-GNOME
gsettings set org.gnome.desktop.interface icon-theme Win7-GNOME
```

## Get the build sources

```sh
git clone --recurse-submodules https://github.com/daffarahman/Win7-GNOME.git
cd Win7-GNOME
```

Python 3, Pillow (listed in `requirements.txt`), and an installed Adwaita icon
theme are required to build. The `artwork/` directory supplies the source images.
The selected original ICO files are included in this repository.

A GNOME icon theme using the supplied Windows 7 Build 7600 artwork. Matching application, folder, drive, and Recycle Bin artwork is selected from Windows 7 first. Unmatched icons fall through to Adwaita and its normal inherited application icons. Control buttons, status icons, and symbolic icons remain inherited from Adwaita, with one explicitly requested exception: Dash to Dock's All Apps button uses a full-color Windows 7 Start orb.

The theme includes 18 folder designs, empty and full Recycle Bin designs, 36 application designs, and four drive/disc designs. Windows filenames are numbered resources rather than GNOME icon names, so `icons.json` records explicit mappings and aliases. Equivalent utilities use the corresponding Windows artwork; applications without a matching role retain their own icons through the fallback chain.

Mappings cover Files, Text Editor, Settings, Terminal (including Alacritty and Ptyxis), Image Viewer, video and audio players, Document Viewer, Archive Manager, Camera, Document Scanner, System Monitor, Disks, Disk Usage Analyzer, Power Statistics, Tweaks, Color Profile Viewer, Volume Control, Print Settings, Hardware Locality, and other common GNOME utilities and games. Shelly and the CachyOS Package Installer use Windows Programs artwork; Wine/Protontricks and Winetricks also use that artwork. The supplied pack has no standalone Calculator icon, so Calculator uses the fallback. Regular mounted-drive and Trash icons in Dash to Dock also use Windows artwork. The full Trash icon is an intentional exception to the shared-name guard because AdwaitaLegacy also categorizes that location icon under status.

`coverage.json` is regenerated from installed launchers and records which Windows resource each matched app uses. At the time of this expansion, 29 of 63 visible installed launchers had a matching Windows resource. The remaining launchers use the Adwaita fallback chain or an application-supplied absolute icon path.

Only `places`, `apps`, and `devices` directories are generated; the device mappings are limited to drives and discs. No symbolic artwork, action icons, status icons, GTK styling, or window decorations are installed. The builder rejects manifest names that overlap action, status, emblem, UI, and symbolic icons anywhere in Adwaita's inheritance chain: icon names are global, so putting them in a different directory alone would not protect controls. Small icons use original embedded ICO frames when available, preferring the highest color depth at each size. Intermediate sizes are downsampled from the next larger source frame; none are upscaled in the generated files. PNG sizes are 16, 22, 24, 32, 48, 64, 96, 128, and 256 pixels when the source has a sufficiently large frame. All currently selected ICO source designs include 256-pixel frames.

The Start orb is installed separately as `view-app-grid-user-symbolic.png` in the application directories, at sizes up to its native 128 pixels. Despite the requested icon name, this is a plain full-color PNG, not recolorable symbolic artwork. Dash to Dock uses this session-specific name; the shared `view-app-grid-symbolic` icon remains inherited. The orb still opens GNOME's All Apps grid. Its source and attribution are recorded in `assets/README.md` and copied into the installed theme as `START-ORB-SOURCE.md`.

## Build and install

Requires Python 3, Pillow, and Adwaita. Sources are included under `artwork/`; the original sibling `Win7_Build7600_Icons` folder remains supported for older local checkouts.

```bash
python3 build_theme.py                    # Build locally and render preview.png
python3 build_theme.py --install          # Install under the user's data directory
python3 build_theme.py --activate         # Install and select in GNOME
python3 build_theme.py --restore-launchers # Restore saved launcher icon fields
```

The generated theme is `build/Win7-GNOME`. Its default installation is `~/.local/share/icons/Win7-GNOME`, respecting `XDG_DATA_HOME` if set. The installer refreshes the GTK icon cache when `gtk-update-icon-cache` is available. On first activation, `previous-settings.json` records the original icon, GTK, and window theme settings. Only the icon theme setting is changed. Repeated activation pauses between theme changes so GNOME Shell can invalidate cached dock and app-grid artwork before loading the rebuilt theme.

Print Settings normally requests the shared `printer` device icon. To apply Windows artwork to just that app, the installer creates a user-local `system-config-printer.desktop` override with `Icon=win7-print-settings`; its other contents are preserved. HP Scan's launcher has a broken absolute icon path, so a user-local `hp-uiscan.desktop` override selects the Windows scanner artwork. Previous user-local launcher contents are saved in `launcher-backups.json`. System launcher files are never edited. `--restore-launchers` restores these changes, leaving any subsequently customized icon field alone.

To restore saved launcher overrides and select Adwaita:

```bash
python3 build_theme.py --restore-launchers
gsettings set org.gnome.desktop.interface icon-theme Adwaita
```

Apps with cached launcher artwork may need to be closed and reopened. Symbolic toolbar and sidebar icons are inherited from Adwaita. Applications that use their own embedded artwork or an absolute icon path can bypass icon themes.

## Adjust the mappings

Edit `icons.json` and run the builder again. Each source path is relative to `artwork/` (or the original sibling `../Win7_Build7600_Icons/` in older local checkouts). Aliases must match an application's `Icon=` launcher field or a folder icon name. Preserve the `Inherits=Adwaita` setting and avoid adding symbolic or control icon names.

The artwork comes from the supplied Windows 7 pack. WhiteSur's naming and directory organization served as the initial compatibility reference; fallback artwork comes from Adwaita through inheritance.
