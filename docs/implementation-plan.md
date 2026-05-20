# ttc-mm-eso Implementation Plan

## Objective

Build a `ttc-mm` CLI that downloads Tamriel Trade Centre price-table data for either EU or NA, installs or refreshes a TTC-compatible addon data source, and lets Master Merchant use TTC as an additional pricing source across its TTC-aware pricing features without polluting LibGuildStore's real sales history.

The preferred design is to let Master Merchant recognize TTC as TTC. Fake LibGuildStore sales history should be avoided unless it becomes necessary for a narrowly scoped fallback mode.

### Reference Implementation

`eso_addon_tools/ttc_mm_converter.py` is a prototype kept for reference only. Its `emit-mm` command injects fake `pricingData` into `ShopkeeperSavedVars` (the MM saved-variable file) — an approach that violates Core Principles 1 and 2 and is not part of the target design. Its Lua parser and row-iteration logic are useful reference for the Downloader and Extractor module. The prototype also confirms that real TTC data files use top-level global assignments (`TamrielTradeCentrePrice.PriceTable = { ... }`) rather than `self.X` patterns, which the production implementation must handle correctly.

## Core Principles

1. Preserve LibGuildStore sales history as the authoritative record of the user's own guild history.
2. Treat TTC as a separate external market data source, not as fabricated MM sale events.
3. Prefer updating an existing official `TamrielTradeCentre` addon installation when available.
4. Fall back to a lightweight TTC compatibility addon only when the official addon is missing.
5. Make any Master Merchant defaults patch opt-in and reversible.
6. Keep the CLI flow simple enough for a non-technical ESO player to run repeatedly.

## Target User Flow

The primary command remains the flow already agreed:

1. User runs `ttc-mm convert`.
2. CLI prompts for region: `EU` or `NA`.
3. CLI prompts for the location of the Master Merchant 3.0 directory or ESO AddOns directory.
4. CLI resolves the real AddOns root from the supplied path.
5. CLI downloads TTC price-table data from:
   - `https://eu.tamrieltradecentre.com/download/PriceTable`
   - `https://us.tamrieltradecentre.com/download/PriceTable`
6. CLI extracts `PriceTable.zip`.
7. CLI installs TTC data into either:
   - an existing official `TamrielTradeCentre` addon folder, or
   - a generated TTC compatibility addon folder.
8. CLI optionally patches MM saved variables to prefer TTC defaults for selected pricing features.
9. CLI reports success, what changed, and what remains optional.

## Architecture

### 1. CLI Application

Responsibilities:

- Parse commands and interactive prompts.
- Resolve region and addon paths.
- Orchestrate download, extraction, install, patch, and validation.
- Provide dry-run and non-interactive flags later.

Initial command surface:

- `ttc-mm convert` — interactive full flow: region prompt, path prompt, download, install, optional patch.
- `ttc-mm validate` — check that installed TTC data files are present, readable, and contain a non-empty price table. Report whether the installation is Mode A or Mode B, and whether MM saved variables are patched.
- `ttc-mm status` — non-destructive summary: installed mode, data file timestamps, and current values of MM TTC-related settings.

Potential later aliases:

- `ttc-mm update` — re-download and reinstall data files without re-running interactive prompts (requires a saved config).
- `ttc-mm uninstall-compat` — remove the Mode B compatibility addon folder and optionally restore MM saved variable backups. No-ops cleanly if no compat addon is present.

### 2. Downloader and Extractor

Responsibilities:

- Download the region-specific TTC `PriceTable` zip.
- Handle HTTP-level failures: surface clear errors on 403, 404, 429 (rate limit), 5xx, timeout, and partial or corrupt body.
- Validate that the download is a zip archive before extracting.
- Extract the expected files:
  - `PriceTableNA.lua` or `PriceTableEU.lua` (only the region-relevant file is required)
  - `ItemLookUpTable_EN.lua` (default locale)
  - other localized `ItemLookUpTable_*.lua` files if present
- Locale selection: default to `EN`. Allow the user to specify an alternative locale; warn if the requested locale file is absent in the zip.
- Preserve original TTC file names so the addon layer can consume them directly.
- TTC Lua file format: data files use top-level global assignments, e.g. `TamrielTradeCentrePrice.PriceTable = { ... }` and `TamrielTradeCentrePrice.ItemLookUpTable = { ... }`. The Lua parser must handle this pattern.
- Idempotency: re-running `convert` always re-downloads and overwrites existing data files. The timestamp embedded in the price table is logged for diagnostics.

### 3. AddOn Path Resolver

Responsibilities:

- Accept either a `MasterMerchant` folder path or an ESO `AddOns` folder path.
- Normalize Linux and Steam/Proton-friendly paths.
- Detect whether the target already contains:
  - `MasterMerchant/`
  - `TamrielTradeCentre/`
- Refuse to install if the directory does not look like an ESO AddOns tree.
- Derive the `SavedVariables` directory from the AddOns path. The standard ESO layout places saved variables at `<ESO live root>/SavedVariables/ShopkeeperSavedVars.lua`, where `<ESO live root>` is the parent of `AddOns`. On Linux/Steam/Proton this resolves through the Proton wine prefix, e.g. `~/.steam/steam/steamapps/compatdata/<APPID>/pfx/drive_c/users/steamuser/Documents/Elder Scrolls Online/live/`. The resolver should walk up from the supplied AddOns path to find the `live` root and locate `SavedVariables/` from there.

### 4. TTC Provider Strategy

The CLI should choose one of two install modes.

#### Mode A: Official TTC Refresh

Use this when `AddOns/TamrielTradeCentre/` already exists.

Responsibilities:

- Update TTC price-table files in place.
- Leave the official TTC addon logic untouched.
- Reuse the addon MM already knows how to query.

Why this is preferred:

- Lowest risk.
- No compatibility shim required.
- MM already consumes `TamrielTradeCentrePrice:GetPriceInfo(itemLink)` when TTC is present.

#### Mode B: TTC Compatibility Addon

Use this when the official TTC addon is missing.

Responsibilities:

- Create a lightweight addon in `AddOns/TamrielTradeCentre/`.
- Expose the smallest API MM needs:
  - global `TamrielTradeCentre`
  - global `TamrielTradeCentrePrice`
  - `TamrielTradeCentrePrice:GetPriceInfo(itemLink)`
- Load and query TTC price-table and lookup files directly.
- Return TTC fields in the shape MM expects:
  - `Avg`
  - `Max`
  - `Min`
  - `EntryCount`
  - `AmountCount`
  - `SuggestedPrice`
  - `SaleAvg`
  - `SaleEntryCount`
  - `SaleAmountCount`
- Verify this field list against the MM source code path that calls `TamrielTradeCentrePrice:GetPriceInfo(itemLink)` before considering the compat addon complete. Any additional fields or nil-checks MM performs on the result table must also be covered.

What the compatibility addon should not do:

- No uploader client.
- No TTC website integration.
- No TTC UI reproduction.
- No fake LibGuildStore sales import.

#### Mode B: Manifest and file structure

The addon must include a `.txt` manifest (e.g. `TamrielTradeCentre.txt`) that lists every Lua file ESO should load. The data files (`PriceTableNA.lua` / `PriceTableEU.lua` and `ItemLookUpTable_EN.lua`) must be declared in this manifest so ESO executes them at addon load time.

Because data files assign to `TamrielTradeCentrePrice.PriceTable` and related globals, the compat addon's bootstrap file must initialize the global table before those files are loaded:

```lua
TamrielTradeCentre = {}
TamrielTradeCentrePrice = {}
```

#### Mode A ↔ Mode B migration

If Mode B is installed and the user later installs the official TTC addon (e.g. via Minion), `AddOns/TamrielTradeCentre/` will contain a mix of compat and official files. The CLI must:

- Detect this condition during `validate` and `status` by checking for the presence of official addon manifest markers alongside compat-generated files.
- Warn the user that the official TTC installation now supersedes the compat addon.
- Direct the user to run `ttc-mm uninstall-compat` to cleanly remove compat-generated files and leave the official addon intact.

### 5. Optional Master Merchant Defaults Patch

This is an opt-in post-install step.

Responsibilities:

- Locate `ShopkeeperSavedVars.lua` (the MM saved-variable file) via the path derived by the AddOn Path Resolver.
- Check whether ESO is currently running; if so, warn the user that any patch will be overwritten by ESO on logout and prompt to confirm or abort.
- Inspect the current values of patch targets in the saved variables.
- Ask whether to patch TTC-related defaults.
- Update only the specific MM settings the user chooses; skip settings already set to the requested value (idempotent).
- Leave unrelated settings untouched.

Patch targets:

- Tooltip TTC visibility
  - `showTTCTipline`
  - optionally `showTTCSalesAverage`
- Price to chat
  - `includeTTCDataPriceToChat`
- Deal calculator
  - `dealCalcToUse`
- Inventory replacement
  - `replacementTypeToUse`
- Voucher pricing
  - `voucherValueTypeToUse`
- AGS pricing
  - `agsSalePriceToUse`

Selectable TTC price modes:

- `TTC Suggested`
- `TTC Average`
- `TTC Sales Average`
- `Leave unchanged`

The patcher should also support:

- backup before write
- restore from backup
- no-op when saved variables do not exist yet

### 6. Optional MM Bridge Addon

This is a later phase, not the initial install path.

Purpose:

- Cover MM paths that are still MM-only even when TTC is installed.
- The main example is vanilla trader post-price autofill, where MM first checks `pricingData` and then falls back to MM average.

Responsibilities:

- Hook or extend the specific MM path that sets pending post price.
- Use TTC as a fallback when MM history pricing is absent.
- Preserve MM behavior when LibGuildStore already has useful data.

This addon should be narrowly scoped and only introduced after the TTC provider path is working reliably.

## Distribution

The target user is a non-technical ESO player. The CLI must be deliverable without requiring a Python installation or command-line setup beyond running a single file.

Preferred approach: package the CLI as a self-contained binary using `PyInstaller` (one-file mode) for each target platform. The binary is downloadable from the project's release page.

Fallback: provide a `requirements.txt` and brief setup instructions for users who prefer to run from source.

The `ttc-mm convert` interactive flow must work with no flags — all required information is gathered via prompts.

## Feature Coverage Matrix

| MM Feature | Current TTC-aware behavior | Mode A (official TTC) | Mode B (compat addon) |
| --- | --- | --- | --- |
| Tooltip TTC lines | Already supported when TTC is present | Yes | Yes — via `GetPriceInfo` shim |
| Deal calculator | Already supports TTC modes | Yes | Yes |
| Inventory replacement | Already supports TTC modes | Yes | Yes |
| Voucher pricing | Already supports TTC modes | Yes | Yes |
| AGS pricing | Already supports TTC modes | Yes | Yes |
| Price to chat | Already supports TTC data | Yes | Yes |
| Vanilla post-price autofill | Not TTC-first today | Later bridge addon | Later bridge addon |
| MM average graphs and sale counts | Based on LibGuildStore sales history | Leave unchanged | Leave unchanged |

## Data Flow

### Preferred Path

1. CLI downloads TTC region data.
2. CLI installs TTC files into official TTC addon or compatibility addon.
3. ESO loads the TTC provider at startup.
4. MM detects `TamrielTradeCentre`.
5. MM calls `TamrielTradeCentrePrice:GetPriceInfo(itemLink)` in TTC-aware features.
6. LibGuildStore continues to provide MM's own guild-history sales data separately.

### Explicit Non-Goal

Do not convert TTC aggregate price-table rows into fake LibGuildStore `sales_data` just to force MM average calculations. That would distort:

- graphs
- sale timestamps
- guild-specific attribution
- outlier trimming
- sale counts
- seller and buyer history

## CLI Prompt Design

### Required Prompts

1. Region: `EU` or `NA`
2. Path to `MasterMerchant` folder or `AddOns` folder

### Conditional Prompts

1. Existing official TTC addon detected:
   - `Update existing TTC addon data?`
2. Official TTC addon missing:
   - `Create TTC compatibility addon?`
3. MM saved variables found:
   - `Patch MM TTC defaults?`
4. If patching defaults:
   - tooltip TTC display: yes or no
   - price-to-chat TTC inclusion: yes or no
   - deal calculator mode
   - inventory replacement mode
   - voucher pricing mode
   - AGS pricing mode

### Suggested Future Non-Interactive Flags

- `--region eu|na`
- `--addons-dir PATH`
- `--mm-dir PATH`
- `--install-mode auto|official|compat`
- `--patch-mm-defaults`
- `--deal-calc ttc-suggested|ttc-average|ttc-sales|leave`
- `--inventory ttc-suggested|ttc-average|ttc-sales|leave`
- `--voucher ttc-suggested|ttc-average|ttc-sales|leave`
- `--ags ttc-suggested|ttc-average|ttc-sales|leave`
- `--dry-run`

## Phased Delivery

### Phase 1: CLI Bootstrap

Deliverables:

- command structure
- interactive prompts
- path resolution
- zip download and extraction
- basic logging and error handling

Exit criteria:

- CLI can download and unpack TTC data for EU and NA.

### Phase 2: Official TTC Refresh Support

Deliverables:

- detection of existing official TTC addon
- in-place TTC file refresh
- validation that expected TTC files are written

Exit criteria:

- Existing TTC users can refresh data with one command.

### Phase 3: TTC Compatibility Addon

Deliverables:

- generated addon manifest
- generated loader code
- `GetPriceInfo(itemLink)` implementation
- TTC lookup and price-table consumption

Exit criteria:

- MM behaves as though TTC is installed for TTC-aware features even without the official TTC addon.

### Phase 4: Optional MM Defaults Patcher

Deliverables:

- saved-variable backup and restore
- selective MM defaults patching
- clear change report

Exit criteria:

- User can opt into TTC defaults without editing saved variables manually.

### Phase 5: MM Bridge Addon

Deliverables:

- narrow hook for post-price autofill and any remaining MM-only gaps
- TTC fallback behavior where MM currently ignores TTC

Exit criteria:

- TTC can assist even in the remaining non-TTC-aware MM pricing paths.

### Phase 6: Packaging and Documentation

Deliverables:

- install guide
- troubleshooting guide
- update strategy
- compatibility matrix

Exit criteria:

- End users can install and maintain the tool without reading source code.

## Risks and Unknowns

1. TTC may change the serialized format of `PriceTable` or lookup files.
2. The compatibility addon must load early enough and expose the right globals so MM detects TTC.
3. Client language and localized lookup tables must match the player's ESO language.
4. Saved variables may not exist until MM has been launched at least once.
5. Linux, Steam, and Proton installations may place ESO files in different locations.
6. The official TTC addon may evolve beyond the minimal API MM currently uses.

## Validation Plan

### Offline Validation

- Verify TTC zip download for both EU and NA.
- Verify extracted TTC files match expected names.
- Verify compatibility addon can parse lookup and price-table files.
- Verify saved-variable patch writes only intended keys.

### In-Game Validation

- TTC tooltip lines appear in MM tooltips.
- Deal calculator can use TTC values.
- Inventory replacement can use TTC values.
- Voucher pricing can use TTC values.
- AGS pricing can use TTC values.
- Price to chat includes TTC data when enabled.
- LibGuildStore history remains unchanged.
- MM graphs and MM average still reflect real guild history only.

## Initial Deliverables

1. `ttc-mm` CLI skeleton
2. TTC downloader and extractor
3. official TTC refresh path
4. TTC compatibility addon generator
5. optional MM defaults patcher
6. documentation for install, update, and rollback

## Open Design Decisions

1. Should `ttc-mm convert` remain the primary command name, or should `convert` and `update` both be supported?
2. Should the compatibility addon always be named `TamrielTradeCentre`, or should it use a distinct internal title while preserving the folder/global names MM expects?
3. Should the defaults patch ask one question per MM feature, or offer a single preset like `TTC Suggested Everywhere`?
4. Should Phase 5 be implemented immediately after TTC compatibility, or deferred until real-world testing identifies MM gaps?

## Recommended Next Step

Start with Phases 1 through 3 and treat the optional MM defaults patch as Phase 4. That gives the project a clean base: TTC data becomes available to MM through the TTC interface first, and only then do we add convenience features and targeted MM bridging.
