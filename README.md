# IR Remote

**In plain words:** IR Remote turns the little USB-C infrared blaster
(ELK Smart / OCRUSTAR "Smart IR Blaster", USB ID `045c:0132`) into a remote
control on your desktop. You teach it the buttons of your real remotes (TV,
soundbar, fan, ...) once, then press them from the window, from a keyboard
shortcut, or from a script.

It is a friendly front end for **elksmart-comm**, which does the actual
talking to the dongle.

## Install

Arch Linux, from this repository:

```
cd packaging/elksmart-comm-git && makepkg -si     # the dongle tool + udev rule
cd ../.. && makepkg -si                           # IR Remote itself
```

`elksmart-comm-git` builds **elksmart-comm** from upstream and also installs a
udev rule (`/usr/lib/udev/rules.d/70-elksmart-ir.rules`) so you can use the
dongle without `sudo`. If the dongle was already plugged in, unplug and replug
it once (the package also tries to apply the rule right away).

Other distributions: install elksmart-comm (from
[usb-drivers](https://git.janouch.name/p/usb-drivers)), PyQt6 and dbus-python,
copy the udev rule, then run `python -m irremote` from this directory.

Start it from the application menu (**Utilities -> IR Remote**) or run `irremote`.

## Learn your first button

1. Plug in the dongle. The bottom-right corner should say **● Dongle ready**.
2. Click the grey **Power** button on the **TV** remote (or **Learn new button**).
3. Click **Start listening**.
4. Hold your TV remote **within 1 cm** of the dongle, pointing at its tip, and
   press the button once (hold it about a second).
5. When it says **Got it!**, click **Test** - your TV should react.
   If it does, click **Save**. If not, click **Retry** and capture it again.

Then just click the button to send it.

## Send from a keyboard shortcut

A global shortcut is already set up for the TV:

| Key            | Does                      |
|----------------|---------------------------|
| `Meta+Ctrl+P`  | TV / Power                |

(Until you have learned TV / Power it shows a notification telling you so.)

To add your own: right-click a button -> **Edit...** -> **Global shortcut**.
Shortcuts work anywhere in Plasma, even with IR Remote closed, and appear in
System Settings -> Keyboard -> Shortcuts. **View -> Shortcuts...** lists them all.
The **In-app key** field is a key that works only while the window is focused.

From the command line:

```
irremote shortcut set "Soundbar" "Volume Up" Meta+Ctrl+Up
irremote shortcut list
irremote shortcut clear "Soundbar" "Volume Up"
```

## Command line (for scripts and power users)

```
irremote send "TV" "Power"            # press a saved button (names are case-insensitive)
irremote send -r 5 "Soundbar" "Volume Up"   # press it 5 times
irremote send-code --nec 20df         # raw NEC: address 20, command df (4 hex digits per press)
irremote send-code -f 36000 <hex>     # raw learned code at 36 kHz
irremote learn                        # capture a button, print its code
irremote learn --save "Fan" "Speed"   # capture and save it
irremote list | status | reset
irremote export ~/ir-remotes.json     # share your remotes
irremote import [--merge] file.json
```

`send` shows a desktop notification if something goes wrong (turn off with
`--no-notify`) and exits non-zero.

## Where things are kept

* Remotes: `~/.config/irremote/remotes.json` (plain JSON; File -> Import/Export to share)
* Global-shortcut launchers: `~/.local/share/applications/irremote-*.desktop`
* Window settings: `~/.config/irremote/irremote.conf`

## Troubleshooting

| What you see | What it means / what to do |
|---|---|
| **Dongle not found** | Plug it in. `lsusb` should list `045c:0132 ELKSMART Smart IR Blaster`. |
| **No permission** | The udev rule isn't applied yet: unplug and replug the dongle. Check with `getfacl /dev/bus/usb/BBB/DDD` - your user should be listed. |
| **Nothing was received** when learning | Hold the remote closer (under 1 cm), aim at the tip of the dongle, hold the button a little longer, try again. Some remotes need fresh batteries. |
| **The dongle isn't answering** | Use **Dongle -> Reset dongle** (or `irremote reset`). If it still fails, unplug and replug it. This can happen after a cancelled learn - the dongle waits for an IR signal and ignores everything else until it gets one; IR Remote resets it automatically in that case. |
| Button "sent" but the TV doesn't react | Learn the button again (captures aren't always perfect), aim the dongle at the TV, and check the frequency (38000 Hz is right for almost everything). |
| **in use by another program** | Only one program can use the dongle at once; wait a moment and retry. |
| Shortcut does nothing | Check System Settings -> Keyboard -> Shortcuts for the entry "IR Remote: TV Power". Run the command (`irremote send "TV" "Power"`) in a terminal to see the error. |

## Technical notes

* Learned codes are stored exactly as elksmart-comm prints them ("Full command").
  NEC codes are stored as address+command pairs and sent with `--nec`.
* Every action holds a lock (`$XDG_RUNTIME_DIR/irremote-<uid>.lock`) so the
  window and shortcut-triggered sends don't fight over the dongle.
* The `045c:0132` dongle answers the learn command with `ff ff ff ff` before
  any IR data; stock elksmart-comm stopped there with "unexpected response".
  `packaging/elksmart-comm-git` carries a small patch that skips it.

## Credits

The dongle protocol is implemented by **elksmart-comm**, part of
[usb-drivers](https://git.janouch.name/p/usb-drivers) by
Přemysl Eric Janouch (0BSD licence; see
`/usr/share/licenses/elksmart-comm-git/LICENSE`). IR Remote only runs it.

IR Remote itself is MIT licensed (see `LICENSE`). The packaging in `packaging/elksmart-comm-git/`
builds elksmart-comm from upstream with one small patch, and keeps its 0BSD licence in
`packaging/elksmart-comm-git/LICENSE.usb-drivers`.
