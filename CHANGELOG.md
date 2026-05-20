# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-20

### Added

- `ttc-mm convert` — download TTC price-table data and install into ESO AddOns
- `ttc-mm validate` — verify installed data integrity and report freshness
- `ttc-mm status` — display current mode, paths, and configuration
- **Mode A**: update data files inside an existing `TamrielTradeCentre/` addon
- **Mode B**: deploy a lightweight compat addon (`TTC_MM_Compat/`) when no TTC client is present
- Bundled Lua compat files: `Init.lua`, `Price.lua`, `Bootstrap.lua`
- Auto-patches `ShopkeeperSavedVars.lua` to enable TTC pricing inside Master Merchant
- NA and EU region support (`--region na|eu`)
