# ttc-mm

A Python CLI tool that downloads [Tamriel Trade Centre](https://tamrieltradecentre.com) price-table data and installs it into your ESO AddOns directory so that [Master Merchant](https://www.esoui.com/downloads/info844-MasterMerchant.html) can use TTC as a pricing source — without needing the TTC Windows client.

## Requirements

- Python 3.10 or later
- Elder Scrolls Online with [Master Merchant](https://www.esoui.com/downloads/info844-MasterMerchant.html) installed

## Installation

```bash
pip install ttc-mm
```

For local development with the desktop GUI entry point:

```bash
pip install -e .
```

## Usage

### Download and install price data

```bash
ttc-mm convert
```

By default the tool detects your ESO AddOns directory automatically. Supply a path to override:

```bash
ttc-mm convert --addons-path "/path/to/Elder Scrolls Online/live/AddOns"
```

Select the server region (default: `na`):

```bash
ttc-mm convert --region eu
```

### Check installation status

```bash
ttc-mm status
```

### Validate installed data

```bash
ttc-mm validate
```

## Desktop GUI

Launch the built-in desktop wrapper with:

```bash
ttc-mm-gui
```

Run a non-graphical prerequisite check with:

```bash
ttc-mm-gui --self-check
```

The GUI wraps the same underlying workflow as the CLI:

- choose your ESO `AddOns` path
- pick `EU` or `NA`
- run `Status`, `Validate`, or `Convert`
- optionally apply a Master Merchant TTC pricing profile during `Convert`

The GUI uses Tkinter, so your Python install needs Tk support available.

## AppImage build

The repository includes a simple AppImage build script for Linux:

```bash
python -m pip install pyinstaller
bash scripts/build-appimage.sh
```

Prerequisites:

- `PyInstaller`
- `appimagetool`
- Tk runtime libraries available to your Python install

The resulting AppImage is written to `dist/ttc-mm-gui-<arch>.AppImage`.

## How it works

`ttc-mm` walks the filesystem to locate your `AddOns/MasterMerchant/` directory and then operates in one of two modes:

- **Mode A**: if `TamrielTradeCentre/` is already present, `ttc-mm` updates the official TTC price-table files in place.
- **Mode B**: if TTC is not installed, `ttc-mm` deploys a lightweight compat `TamrielTradeCentre/` addon so Master Merchant can read TTC data.

After installing the data files, `ttc-mm` can patch Master Merchant saved variables to enable TTC pricing inside the addon.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE.md).

ESO addon source files in `eso_addon_tools/` are used for development reference only and are not distributed with this package.
