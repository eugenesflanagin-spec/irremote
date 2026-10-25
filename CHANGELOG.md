# Changelog

All notable changes to IR Remote. Versions follow [semantic versioning](https://semver.org/).

## 1.1.0 - 2026-10-25

### Added
- **Picture of your remote ("visual remote").** A remote can be shown as a
  drawing of the real remote: click a button on the picture to send it.
  Buttons that aren't learned yet are dim with a dashed outline; hovering shows
  the name and whether it's learned or has a shortcut; right-click offers
  Learn again, Assign shortcut, Edit code and Clear. Sending flashes the button.
- Two built-in pictures: **TV remote - VIZIO / onn. (VQM55C-1004)** and
  **Android TV box remote - onn. 4K Pro (Google TV)**.
- **Use my own picture...**: load a photo of any remote and mark its buttons
  (add, move, resize, rename, delete round or square hotspots). The photo is
  copied to `~/.config/irremote/photos/`.
- **Learn all...**: walks through every button of a picture remote in turn,
  highlighting it ("Press VOLUME UP on your remote"), with Skip, Retry, Back,
  Test and Finish, and progress ("Button 7 of 22"). Each code is saved as soon
  as it is captured. Power, Volume, Mute and Input come first.
- View -> Picture / Grid (Ctrl+1 / Ctrl+2); the picture is the default for
  remotes that have one. Saved buttons that aren't on the picture are listed
  next to it as "Other buttons".
- Add remote now asks which picture to use (none/grid, built-in, own photo);
  Remote -> Picture... changes it later.
- Layouts are plain JSON files; extra ones can go in
  `~/.config/irremote/layouts/`.
- Command line: `irremote layouts`, `irremote layout REMOTE [ID|none]`,
  and `irremote send --dry-run` (checks a button without sending anything).
- README: why some buttons can't be learned (Bluetooth), and line of sight.

### Changed
- remotes.json is now version 2: a remote may have a `"layout"` (a built-in
  id or its own photo layout). Version 1 files load unchanged; the first save
  keeps a copy as `remotes.json.v1-backup`.

## 1.0.0 - 2026-10-25

First release.

- Desktop remote control for ELK Smart / OCRUSTAR USB IR blasters
  (`045c:0132`), driven by elksmart-comm.
- Learn buttons from your remotes, send them from the window, the tray,
  in-app keys or KDE Plasma global shortcuts.
- Command line: send, send-code, learn, list, status, reset, import/export,
  shortcut set/clear/list.
- `packaging/elksmart-comm-git` with a udev rule and a patch for the learn
  handshake of the `045c:0132` dongle.
