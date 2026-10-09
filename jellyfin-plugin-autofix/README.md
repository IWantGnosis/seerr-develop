# AutoFix: Jellyfin Plugin

**AutoFix** is a Jellyfin .NET 8 plugin designed to permanently fix messy torrent/download filenames (with dots, release groups, codecs, audio tags) and prevent blank grey placeholder boxes.

---

## 🚀 Key Features

1. **Pre-Scan Name Sanitizer:**
   - Strips 40+ release tags (`1080p`, `2160p`, `4K`, `WEB-DL`, `10bit`, `Dual Audio`, `MoviesMod.zone`, `BollyFlix`, `RARBG`, etc.).
   - Converts dots (`.`) and underscores (`_`) into clean spaces.
   - Extracts clean movie title and release year before Jellyfin queries metadata providers.

2. **Multi-Tier TMDb Fallback Matcher:**
   - Queries TMDb with clean title + year.
   - Falls back to clean title without year if unreleased or year differs.
   - Falls back to franchise root keywords for multi-part titles.
   - Binds `ProviderIds["Tmdb"]` and `ProviderIds["Imdb"]` to the media item.

3. **Auto Artwork Injector:**
   - Automatically downloads and injects TMDb Primary Posters, Backdrops, and Logos.
   - Guarantees movies never appear as grey squares.

4. **Automated Healing Scheduled Task:**
   - Adds **"AutoFix: Heal Missing Posters & Metadata"** under **Dashboard → Scheduled Tasks**.
   - Runs daily or on-demand to heal any existing items missing artwork.

5. **Optional In-Place Renamer:**
   - Configurable option in the plugin dashboard to safely rename media files on disk to standard naming:
     `Movie Title (Year) [tmdbid-XXXXX].mkv`

---

## 📦 Installation on Jellyfin (Docker / Linux Server)

### Step 1: Copy DLL to Server
The compiled plugin DLL is located at:
`jellyfin-plugin-autofix/bin/Release/net8.0/Jellyfin.Plugin.AutoFix.dll`

On your home server (`192.168.29.75`), create the plugin folder in your Jellyfin data directory:
```bash
# In your Jellyfin config directory (e.g. /home/home/jellyfin/config/plugins):
mkdir -p /path/to/jellyfin/config/plugins/AutoFix
```

Copy `Jellyfin.Plugin.AutoFix.dll` into that directory:
```bash
cp Jellyfin.Plugin.AutoFix.dll /path/to/jellyfin/config/plugins/AutoFix/
```

### Step 2: Restart Jellyfin
```bash
docker restart jellyfin
```

### Step 3: Verify & Configure
1. Open Jellyfin Dashboard $\rightarrow$ **Plugins**.
2. Click on **AutoFix** to adjust settings (Sanitizer, Fuzzy Matcher, Artwork Injector, Custom tags).
3. Under **Scheduled Tasks**, run **AutoFix: Heal Missing Posters & Metadata** to heal any existing library items.
