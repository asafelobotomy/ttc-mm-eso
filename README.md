# ttc-mm

A Python CLI tool that downloads [Tamriel Trade Centre](https://tamrieltradecentre.com) price-table data and installs it into your ESO AddOns directory so that [Master Merchant](https://www.esoui.com/downloads/info844-MasterMerchant.html) can use TTC as a pricing source — without needing the TTC Windows client.

## Requirements

- Python 3.10 or later
- Elder Scrolls Online with [Master Merchant](https://www.esoui.com/downloads/info844-MasterMerchant.html) installed

## Installation

```bash
pip install ttc-mm
```

## Usage

### Download and install price data

```bash
ttc-mm convert
```

By default the tool detects your ESO AddOns directory automatically. Supply a path to override:

```bash
ttc-mm convert --path "/path/to/Elder Scrolls Online/live/AddOns"
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

## How it works

`ttc-mm` walks the filesystem to locate your `AddOns/MasterMerchant/` directory and then operates in one of two modes:

| Mode | Condition | Behaviour |
|------|-----------|-----------|
| **A** | `TamrielTradeCentre/` addon is present | Downloads and overwrites the official TTC price-table files in-place |
| **B** | No TTC addon found | Deploys a lightweight compat addon (`TTC_MM_Compat/`) that exposes the same Lua globals MM expects |

After installing the data files, `ttc-mm` automatically patches `ShopkeeperSavedVars.lua` to enable TTC pricing inside Master Merchant.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE.md).

ESO addon source files in `eso_addon_tools/` are used for development reference only and are not distributed with this package.
