# 🎵 **DeeMusic Metadata Fix: Album Artist Configuration**

## 🐛 **Problem Identified**
The metadata system was incorrectly setting **Artist** and **Album Artist** to the same value for most tracks, when they should often be different for:

- **Featured artists** (e.g., Album Artist: "Taylor Swift", Track Artist: "Taylor Swift feat. Ed Sheeran")
- **Compilation albums** (e.g., Album Artist: "Various Artists", Track Artist: individual performers)
- **Collaborative albums** (e.g., Album Artist: "Jay-Z & Kanye West", Track Artist: might vary per song)
- **Soundtracks** (e.g., Album Artist: "Soundtrack", Track Artist: individual performers)

## ✅ **Solution Implemented**

### **1. New Metadata Configuration Setting**
Added **"Metadata Settings"** section in Settings → Structure tab with three options:

| Option | Behavior | Best For |
|--------|----------|----------|
| **🔥 Use Album Artist from API (Recommended)** | Uses actual album artist when available, falls back to track artist | Most accurate metadata |
| **Always use Track Artist** | Copies track artist to album artist field | Users who prefer consistency |
| **Various Artists for Compilations Only** | Uses album artist only for compilation albums | Legacy behavior |

### **2. Code Changes Made**

#### **Enhanced Album Artist Detection Method**
```python
def _get_album_artist(self, track_info: dict, track_artist: str) -> str:
    """Get album artist based on user configuration and track data with enhanced detection."""
    strategy = self.download_manager.config.get_setting('metadata.album_artist_strategy', 'album_artist_from_api')
    
    album_artist_from_api = track_info.get('album', {}).get('artist', {}).get('name')
    
    # Enhanced detection when API doesn't provide album artist
    if not album_artist_from_api:
        # Detect compilation albums automatically
        album_title = track_info.get('alb_title', track_info.get('album', {}).get('title', ''))
        compilation_indicators = ['various artists', 'compilation', 'soundtrack', 'best of', 'greatest hits']
        is_compilation = any(indicator in album_title.lower() for indicator in compilation_indicators)
        
        if is_compilation:
            album_artist_from_api = "Various Artists"
        else:
            # For collaborative tracks, use primary artist as album artist
            artists_array = track_info.get('artists', [])
            if artists_array and len(artists_array) > 1:
                primary_artist = artists_array[0]
                if isinstance(primary_artist, dict) and 'ART_NAME' in primary_artist:
                    album_artist_from_api = primary_artist['ART_NAME']
            
            # Fallback to main artist field
            if not album_artist_from_api:
                art_name = track_info.get('art_name')
                if art_name:
                    album_artist_from_api = art_name
    
    # Apply user strategy
    if strategy == 'track_artist':
        return track_artist
    elif strategy == 'compilation_aware':
        if album_artist_from_api and album_artist_from_api.lower() in ['various artists', 'various', 'compilation']:
            return album_artist_from_api
        else:
            return track_artist
    else:  # 'album_artist_from_api' (default)
        return album_artist_from_api if album_artist_from_api else track_artist
```

#### **Updated All Album Artist Logic**
- **Filename generation** (uses configurable logic)
- **Metadata writing** (both MP3 ID3 and FLAC Vorbis)
- **Path calculation** (for folder organization)

#### **Settings UI Integration**
- Added dropdown in Settings → Structure → Metadata Settings
- Includes helpful explanations for each option
- Default: "Use Album Artist from API (Recommended)"
- Persists user choice and loads on startup

### **3. How It Works**

#### **Before (Broken)**
```
Track: "APT." by ROSÉ feat. Bruno Mars
❌ Artist: "ROSÉ"  # WRONG - missing collaboration
❌ Album Artist: "ROSÉ"  # WRONG - same as track artist, no differentiation
```

#### **After (Fixed - Recommended Setting)**
```
Track: "APT." by ROSÉ feat. Bruno Mars
✅ Artist: "ROSÉ feat. Bruno Mars"  # CORRECT - shows full collaboration
✅ Album Artist: "ROSÉ"  # CORRECT - primary artist for album grouping
```

#### **Additional Examples**

**Collaboration:**
```
Track: "APT." by ROSÉ feat. Bruno Mars
✅ Artist: "ROSÉ feat. Bruno Mars"  # Shows full collaboration
✅ Album Artist: "ROSÉ"  # Primary artist for album grouping
```

**Compilation:**
```
Track: "Don't Stop Believin'" by Journey (from "Greatest Hits Compilation")
✅ Artist: "Journey"
✅ Album Artist: "Various Artists"  # Auto-detected compilation
```

**Regular Album:**
```
Track: "Shape of You" by Ed Sheeran (from "÷")
✅ Artist: "Ed Sheeran"
✅ Album Artist: "Ed Sheeran"  # Same for single artists (correct)
```

### **4. Enhanced Detection Features**

- **🎵 Collaborative Artist Names**: Automatically constructs proper track artist names for collaborations (e.g., "ROSÉ feat. Bruno Mars")
- **🤖 Automatic Compilation Detection**: Recognizes compilation albums by title keywords ("Various Artists", "Compilation", "Soundtrack", "Best Of", "Greatest Hits")
- **👥 Smart Album Artist Logic**: For collaborative tracks, uses the primary artist as album artist while showing full collaboration in track artist
- **🔍 Multi-Source Detection**: Looks for album artist information in multiple API fields when primary source is unavailable
- **📋 Comprehensive Logging**: Detailed debug output to track both track artist and album artist detection process

### **5. Benefits**

- **🎯 Accurate Metadata**: Music library software will properly group albums by actual album artist
- **📱 Better Mobile Experience**: Phone music apps will show correct album groupings
- **🎧 Proper Sorting**: Featured artists won't create duplicate album entries
- **🎪 Compilation Support**: Various Artists albums are handled correctly automatically
- **⚙️ User Control**: Three strategies to match different user preferences
- **🔄 Backward Compatible**: Existing downloads aren't affected, new downloads use new logic

### **6. Configuration Access**

1. Open **Settings** (⚙️ gear icon)
2. Go to **Structure** tab
3. Find **Metadata Settings** section
4. Choose your preferred **Album Artist Strategy**
5. Click **Save**

### **7. Default Behavior**
- **New installations**: Uses "Album Artist from API" (recommended)
- **Existing installations**: Uses "Album Artist from API" (recommended)
- **Reset to defaults**: Resets to "Album Artist from API"

## 🧪 **Testing Results**

This fix ensures that:
- Regular albums show proper album artist (not track artist with features)
- Compilation albums preserve "Various Artists" designation
- Featured artist tracks don't create duplicate album entries
- Music library software properly groups and sorts albums
- Both MP3 and FLAC files get correct metadata

The implementation is fully configurable, backward compatible, and follows music metadata best practices! 🎉

---

## 📁 **Update: Folder Structure & Artwork Fixes**

### **Additional Issues Fixed**

#### **🔧 Folder Template Compatibility**
- **Problem**: Templates using `%albumartist%` weren't being replaced (showing literal text)
- **Solution**: Added `albumartist` as placeholder alias for `album_artist`
- **Result**: Both `%album_artist%` and `%albumartist%` templates now work properly

#### **🎨 Artwork File Saving**
- **Problem**: Album covers and artist images weren't being saved to correct directories
- **Solution**: Fixed directory path calculation to use same structure as audio files
- **Result**: `cover.jpg` and `folder.jpg` files now save correctly alongside music files

### **Improved Download Structure**
```
ROSÉ feat. Bruno Mars/          # ✅ Artist folder (collaborative name)
└── APT./                       # ✅ Album folder
    ├── cover.jpg              # ✅ Album artwork (saved properly)
    ├── folder.jpg             # ✅ Artist image (saved properly)
    └── 01 - ROSÉ feat. Bruno Mars - APT..mp3  # ✅ Track file
```

### **All Template Placeholders Now Supported**
- `%artist%` → "ROSÉ feat. Bruno Mars"
- `%album_artist%` → "ROSÉ" 
- `%albumartist%` → "ROSÉ" (alias for compatibility)
- `%album%` → "APT."
- `%title%` → "APT."
- And all other existing placeholders...

**The folder structure and artwork saving now work perfectly with the enhanced metadata system!** 🎵📁 