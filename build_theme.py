#!/usr/bin/env python3
"""Build a small Windows 7 icon theme that inherits Adwaita controls."""

import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "artwork"
if not SOURCE.is_dir():
    SOURCE = ROOT.parent / "Win7_Build7600_Icons"
THEME = "Win7-GNOME"
FALLBACK = "Adwaita"
SIZES = (16, 22, 24, 32, 48, 64, 96, 128, 256)
MARKER = ".win7-gnome-managed"
# Dash to Dock requests this session-specific name for its Show Applications
# button. A plain PNG preserves the orb's colors despite the requested suffix;
# this is not a recolorable .symbolic.png and does not replace the shared grid.
DOCK_ICON = "view-app-grid-user-symbolic"
DOCK_SOURCE = ROOT / "assets" / "win7-start-orb.png"
# AdwaitaLegacy also lists the full Trash icon under status. It represents
# the user-requested Trash location, so this one shared name is intentional.
PLACE_OVERRIDE_EXCEPTIONS = {"user-trash-full"}


def data_home():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def data_directories():
    return [data_home(), *[Path(p) for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if p]]


def extract_frame(path, size):
    """Use an exact native frame, otherwise downsample the next larger frame."""
    with Image.open(path) as ico:
        sizes = sorted(ico.ico.sizes(), key=lambda xy: (xy[0], xy[1]))
        larger = [xy for xy in sizes if xy[0] >= size and xy[1] >= size]
        if not larger:
            raise ValueError(f"{path}: no native frame large enough for {size}px")
        chosen = larger[0]
        # Some Windows ICOs contain 4-, 8-, and 32-bit frames at the same size.
        # Pillow's default can select a legacy low-color frame; prefer true color.
        depth = max(entry.bpp for entry in ico.ico.entry if entry.dim == chosen)
        frame = ico.ico.getimage(chosen, bpp=depth).convert("RGBA")
    if frame.size != (size, size):
        frame = frame.resize((size, size), Image.Resampling.LANCZOS)
    return frame


def check_manifest(manifest):
    if set(manifest) != {"apps", "places", "devices"}:
        raise ValueError("Only application, folder, and drive contexts may be replaced")
    names = set()
    for icons in manifest.values():
        for name, entry in icons.items():
            source = (SOURCE / entry["source"]).resolve()
            if not source.is_relative_to(SOURCE.resolve()) or not source.is_file():
                raise ValueError(f"Invalid icon source: {source}")
            for alias in [name, *entry["aliases"]]:
                if not alias or "/" in alias or "\\" in alias or "symbolic" in alias:
                    raise ValueError(f"Invalid full-color icon name: {alias}")
                if alias in names:
                    raise ValueError(f"Duplicate icon name: {alias}")
                names.add(alias)
    # Icon lookup uses names globally, so context directories alone do not
    # prevent a folder/app name from replacing an action icon with that name.
    protected = set()
    for fallback in inherited_directories():
        protected.update({
            p.stem
            for p in fallback.rglob("*")
            if p.suffix in {".svg", ".png", ".xpm"}
            and (
                {"actions", "status", "emblems", "ui"}.intersection(p.relative_to(fallback).parts[:-1])
                or "-symbolic" in p.stem
            )
        })
    collisions = (names & protected) - PLACE_OVERRIDE_EXCEPTIONS
    if collisions:
        raise ValueError(f"These names would replace inherited controls: {sorted(collisions)}")


def write_index(destination, manifest):
    contexts = {"places": "Places", "apps": "Applications", "devices": "Devices"}
    directories = [f"{size}x{size}/{context}" for size in SIZES for context in manifest]
    lines = [
        "[Icon Theme]", f"Name={THEME}",
        f"Comment=Windows 7 artwork for matching folders, apps and drives; {FALLBACK} fallback.",
        f"Inherits={FALLBACK}", "Example=folder", "Directories=" + ",".join(directories), "",
    ]
    for size in SIZES:
        for context in manifest:
            label = contexts[context]
            lines += [f"[{size}x{size}/{context}]", f"Size={size}", f"Context={label}", "Type=Fixed", ""]
    (destination / "index.theme").write_text("\n".join(lines))


def render_preview(destination, manifest):
    entries = [(context, name, entry) for context, icons in manifest.items() for name, entry in icons.items()]
    entries.append(("apps", DOCK_ICON, {"label": "Start / All Apps"}))
    columns, cell_w, cell_h = 4, 218, 174
    image = Image.new("RGB", (columns * cell_w, 102 + ((len(entries) + columns - 1) // columns) * cell_h), "#f1f3f5")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        title_font = ImageFont.truetype("DejaVuSans.ttf", 27)
        small = ImageFont.truetype("DejaVuSans.ttf", 12)
    except OSError:
        font = title_font = small = ImageFont.load_default()
    draw.text((24, 18), "Windows 7 for GNOME", font=title_font, fill="#17212c")
    draw.text((24, 58), f"Folders, apps, drives and Start orb • {FALLBACK} controls inherited", font=font, fill="#52606d")
    for index, (context, name, entry) in enumerate(entries):
        x, y = index % columns * cell_w, 102 + index // columns * cell_h
        available = [size for size in SIZES if (destination / f"{size}x{size}" / context / f"{name}.png").is_file()]
        chosen = next((size for size in available if size >= 96), available[-1])
        with Image.open(destination / f"{chosen}x{chosen}" / context / f"{name}.png") as source:
            icon = source.convert("RGBA")
        icon.thumbnail((96, 96), Image.Resampling.LANCZOS)
        image.paste(icon, (x + (cell_w - icon.width) // 2, y + 3 + (96 - icon.height) // 2), icon)
        draw.text((x + cell_w / 2, y + 111), entry["label"], font=font, fill="#17212c", anchor="mt")
        draw.text((x + cell_w / 2, y + 138), name, font=small, fill="#52606d", anchor="mt")
    image.save(ROOT / "preview.png")


def replace_managed(staging, destination):
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not (destination / MARKER).is_file():
            raise ValueError(f"Refusing to overwrite an unrelated directory: {destination}")
        shutil.rmtree(destination)
    staging.rename(destination)


def write_dock_icon(destination):
    """Install the explicitly requested dock-only exception to inherited UI."""
    with Image.open(DOCK_SOURCE) as source:
        orb = source.convert("RGBA")
    for size in SIZES:
        if size > min(orb.size):
            continue
        folder = destination / f"{size}x{size}" / "apps"
        folder.mkdir(parents=True, exist_ok=True)
        orb.resize((size, size), Image.Resampling.LANCZOS).save(folder / f"{DOCK_ICON}.png")
    shutil.copy2(ROOT / "assets" / "README.md", destination / "START-ORB-SOURCE.md")
    shutil.copy2(ROOT / "SOURCE.md", destination / "SOURCE.md")


def build(manifest):
    build_root = ROOT / "build"
    build_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=build_root) as temporary:
        staging = Path(temporary) / THEME
        staging.mkdir()
        write_index(staging, manifest)
        (staging / MARKER).write_text("Generated by Win7-GNOME/build_theme.py\n")
        maximum_sizes = {}
        for icons in manifest.values():
            for name, entry in icons.items():
                with Image.open(SOURCE / entry["source"]) as source:
                    maximum_sizes[name] = max(min(xy) for xy in source.ico.sizes())
        for size in SIZES:
            for context, icons in manifest.items():
                folder = staging / f"{size}x{size}" / context
                folder.mkdir(parents=True)
                for name, entry in icons.items():
                    if size > maximum_sizes[name]:
                        continue
                    extract_frame(SOURCE / entry["source"], size).save(folder / f"{name}.png")
                    for alias in entry["aliases"]:
                        (folder / f"{alias}.png").symlink_to(f"{name}.png")
        write_dock_icon(staging)
        shutil.copy2(ROOT / "icons.json", staging / "sources.json")
        render_preview(staging, manifest)
        destination = build_root / THEME
        replace_managed(staging, destination)
    print(f"Built: {destination}")
    write_coverage(manifest)
    return destination


def theme_directory(name):
    roots = [data_home() / "icons", Path.home() / ".icons"]
    roots += [Path(p) / "icons" for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if p]
    return next((p / name for p in roots if (p / name / "index.theme").is_file()), None)


def fallback_directory():
    return theme_directory(FALLBACK)


def inherited_directories():
    pending, seen = [FALLBACK, "hicolor"], set()
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        directory = theme_directory(name)
        if directory:
            yield directory
            index = configparser.ConfigParser(interpolation=None, strict=False)
            index.read(directory / "index.theme")
            pending += [value.strip() for value in index.get("Icon Theme", "Inherits", fallback="").split(",") if value.strip()]


def launchers():
    found = {}
    for root in data_directories():
        for path in sorted((root / "applications").glob("*.desktop")):
            found.setdefault(path.name, path)
    return found


def desktop_entry(text):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(text)
    return parser["Desktop Entry"]


def replace_launcher_icon(text, icon):
    lines = text.splitlines(keepends=True)
    in_entry = False
    for index, line in enumerate(lines):
        if line.startswith("["):
            in_entry = line.strip() == "[Desktop Entry]"
        elif in_entry and line.startswith("Icon="):
            lines[index] = f"Icon={icon}\n"
            return "".join(lines)
    raise ValueError("Launcher has no Icon field in its Desktop Entry section")


def install_launcher_icons(manifest):
    # A dedicated launcher name avoids replacing shared device/control names
    # such as 'printer' while still styling that application's launcher.
    backup_file = ROOT / "launcher-backups.json"
    backups = json.loads(backup_file.read_text()) if backup_file.exists() else {}
    available = launchers()
    for name, entry in manifest["apps"].items():
        for filename in entry.get("desktop_files", []):
            if Path(filename).name != filename:
                raise ValueError(f"Invalid launcher filename: {filename}")
            source = available.get(filename)
            if not source:
                continue
            destination = data_home() / "applications" / filename
            text = source.read_text()
            updated = replace_launcher_icon(text, name)
            if filename not in backups:
                backups[filename] = {"previous": destination.read_text() if destination.exists() else None, "icon": name}
                backup_file.write_text(json.dumps(backups, indent=2) + "\n")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(updated)
            print(f"Application icon: {filename} -> {name}")


def restore_launcher_icons():
    backup_file = ROOT / "launcher-backups.json"
    if not backup_file.exists():
        return
    backups = json.loads(backup_file.read_text())
    for filename, backup in list(backups.items()):
        destination = data_home() / "applications" / filename
        if destination.exists():
            if desktop_entry(destination.read_text()).get("Icon") != backup["icon"]:
                print(f"Keeping subsequently edited launcher: {filename}")
                continue
            if backup["previous"] is None:
                destination.unlink()
            else:
                destination.write_text(backup["previous"])
        del backups[filename]
    backup_file.write_text(json.dumps(backups, indent=2) + "\n")


def write_coverage(manifest):
    by_icon = {alias: entry for icons in manifest.values() for name, entry in icons.items() for alias in [name, *entry["aliases"]]}
    by_desktop = {filename: entry for entry in manifest["apps"].values() for filename in entry.get("desktop_files", [])}
    rows = []
    for filename, path in sorted(launchers().items()):
        entry = desktop_entry(path.read_text())
        if entry.get("NoDisplay", "false").lower() == "true" or entry.get("Hidden", "false").lower() == "true":
            continue
        icon = entry.get("Icon", "")
        match = by_desktop.get(filename) or by_icon.get(icon)
        rows.append({"name": entry.get("Name", filename), "desktop_file": filename, "icon": icon, "selection": "Windows 7" if match else "application-supplied path" if icon.startswith("/") else "Adwaita fallback chain", "source": match["source"] if match else None})
    (ROOT / "coverage.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"Installed app coverage: {sum(row['source'] is not None for row in rows)} of {len(rows)} visible launchers have matching Windows 7 artwork")


def get_setting(schema, key):
    return subprocess.check_output(["gsettings", "get", schema, key], text=True).strip()


def install(built, manifest, activate):
    if not fallback_directory():
        raise RuntimeError(f"Install {FALLBACK} first: this theme inherits its controls and other icons")
    parent = data_home() / "icons"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / THEME
    with tempfile.TemporaryDirectory(prefix=".win7-install-", dir=parent) as temporary:
        staging = Path(temporary) / THEME
        shutil.copytree(built, staging, symlinks=True)
        cache_tool = shutil.which("gtk-update-icon-cache")
        if cache_tool:
            subprocess.run([cache_tool, "--force", "--include-image-data", str(staging)], check=True)
        replace_managed(staging, destination)
    print(f"Installed: {destination}")
    install_launcher_icons(manifest)
    if activate:
        saved = ROOT / "previous-settings.json"
        before = {
            "icon-theme": get_setting("org.gnome.desktop.interface", "icon-theme"),
            "gtk-theme": get_setting("org.gnome.desktop.interface", "gtk-theme"),
            "window-theme": get_setting("org.gnome.desktop.wm.preferences", "theme"),
        }
        if not saved.exists() and before["icon-theme"] != repr(THEME):
            saved.write_text(json.dumps(before, indent=2) + "\n")
        try:
            if before["icon-theme"] == repr(THEME):
                subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", FALLBACK], check=True)
                # GNOME Shell reads settings asynchronously. Let it process the
                # fallback theme before selecting the rebuilt theme again.
                time.sleep(1.5)
        finally:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", THEME], check=True)
        after = get_setting("org.gnome.desktop.interface", "icon-theme")
        if after != repr(THEME):
            raise RuntimeError(f"GNOME did not select {THEME}: {after}")
        if before["gtk-theme"] != get_setting("org.gnome.desktop.interface", "gtk-theme") or before["window-theme"] != get_setting("org.gnome.desktop.wm.preferences", "theme"):
            raise RuntimeError("The GTK or window theme unexpectedly changed")
        print(f"Activated: {THEME} (GTK and window themes unchanged)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Install for the current user")
    parser.add_argument("--activate", action="store_true", help="Install and select the theme in GNOME")
    parser.add_argument("--restore-launchers", action="store_true", help="Restore application launcher icons saved before installation")
    args = parser.parse_args()
    if args.restore_launchers:
        restore_launcher_icons()
        return
    manifest = json.loads((ROOT / "icons.json").read_text())
    check_manifest(manifest)
    built = build(manifest)
    if args.install or args.activate:
        install(built, manifest, args.activate)


if __name__ == "__main__":
    main()
