# 🎵 Spotify Playlist Conversion Guide

DeeMusic now supports converting Spotify playlists to Deezer tracks! This feature allows you to paste a Spotify playlist URL into the search bar and automatically find matching tracks on Deezer for download.

## 📋 Table of Contents

1. [Setup Requirements](#setup-requirements)
2. [Getting Spotify API Credentials](#getting-spotify-api-credentials)
3. [Configuring DeeMusic](#configuring-deemusic)
4. [Using Playlist Conversion](#using-playlist-conversion)
5. [Understanding Match Quality](#understanding-match-quality)
6. [Troubleshooting](#troubleshooting)

---

## 🔧 Setup Requirements

### Prerequisites
- **DeeMusic v1.0.3+** with Spotify integration
- **Spotify Developer Account** (free)
- **Active Deezer ARL token** (for downloading matched tracks)

### Supported Playlist URLs
The following Spotify playlist URL formats are supported:
- `https://open.spotify.com/playlist/PLAYLIST_ID`
- `https://spotify.com/playlist/PLAYLIST_ID`
- `spotify:playlist:PLAYLIST_ID`

---

## 🎯 Getting Spotify API Credentials

### Step 1: Create a Spotify Developer Account
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Log in with your Spotify account (or create one if needed)
3. Accept the Terms of Service if prompted

### Step 2: Create a New App
1. Click **"Create App"**
2. Fill in the app details:
   - **App name**: `DeeMusic Playlist Converter` (or any name you prefer)
   - **App description**: `Convert Spotify playlists to Deezer tracks`
   - **Website**: Leave blank or use `http://localhost`
   - **Redirect URI**: Leave blank (not needed for playlist conversion)
3. Check the Terms of Service agreement
4. Click **"Create"**

### Step 3: Get Your Credentials
1. Click on your newly created app
2. Copy the **Client ID** (visible immediately)
3. Click **"Show Client Secret"** and copy the **Client Secret**
4. **Keep these credentials secure** - treat them like passwords

---

## ⚙️ Configuring DeeMusic

### Step 1: Open Settings
1. Launch DeeMusic
2. Click the **Settings** button (⚙️) in the top-right corner
3. Navigate to the **"Spotify"** tab

### Step 2: Enter Your Credentials
1. Paste your **Client ID** in the corresponding field
2. Paste your **Client Secret** in the corresponding field
3. Optionally check **"Show Client Secret"** to verify it's entered correctly

### Step 3: Test Connection
1. Click **"Test Spotify Connection"**
2. If successful, you'll see "Connected successfully!" message
3. The status should show **"Configured"** in green

### Step 4: Configure Conversion Settings
- **Minimum Match Score**: Set the threshold for accepting matches (50-100%)
  - `90%+`: Excellent matches only
  - `70%+`: Good matches (recommended)
  - `50%+`: Include fair matches
- **Show tracks that couldn't be matched**: Display failed matches for review
- **Automatically download converted playlists**: Start downloads immediately after conversion

### Step 5: Save Settings
Click **"Save"** to store your configuration.

---

## 🚀 Using Playlist Conversion

### Step 1: Get a Spotify Playlist URL
1. Open Spotify (web, desktop, or mobile)
2. Navigate to any playlist
3. Click **"Share"** → **"Copy link to playlist"**
4. The URL will look like: `https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M`

### Step 2: Convert in DeeMusic
1. Open DeeMusic and go to the **Search** page
2. **Paste the Spotify playlist URL** into the search bar
3. Press **Enter** or click search
4. DeeMusic will automatically detect it's a Spotify URL and start conversion

### Step 3: Monitor Progress
- A progress bar will show the conversion status
- You'll see messages like "Searching for: Song Name by Artist"
- The process may take 1-5 minutes depending on playlist size

### Step 4: Review Results
After conversion, you'll see:
- **Playlist name** and conversion statistics
- **Success rate** (e.g., "Found 45 of 50 tracks on Deezer (90% match rate)")
- **Complete track list** with match quality indicators

### Step 5: Download Tracks
- **Individual tracks**: Click the download button on any track
- **Multiple tracks**: Select tracks and use batch download
- **Entire playlist**: If auto-download is enabled, downloading starts automatically

---

## 🎯 Understanding Match Quality

### Match Score Indicators
When you hover over converted tracks, you'll see match quality:

| Score Range | Quality | Description |
|-------------|---------|-------------|
| **90-100%** | ⭐ Excellent | Perfect or near-perfect match |
| **70-89%** | ✅ Good | Very likely to be correct |
| **50-69%** | ⚠️ Fair | Probably correct, but verify |
| **0-49%** | ❌ Poor | Low confidence, manual check recommended |

### What Gets Matched
The system compares:
- **Track title** (40% weight)
- **Artist name** (30% weight)
- **Album name** (20% weight)
- **Duration** (10% weight)

### Failed Matches
Tracks that couldn't be matched will appear with:
- Red background highlighting
- "No match found on Deezer" tooltip
- Download button disabled

---

## 🔧 Troubleshooting

### "Playlist Conversion Failed" Error

#### Problem: Invalid Credentials
**Error**: "Invalid Client ID or Client Secret"
**Solution**: 
1. Verify credentials are copied correctly (no extra spaces)
2. Check that your Spotify app is not in Development Mode restrictions
3. Generate new credentials if needed

#### Problem: Network Issues
**Error**: "Connection failed" or timeout
**Solution**:
1. Check internet connection
2. Try using a VPN if geo-restricted
3. Disable proxy settings temporarily

#### Problem: Playlist Not Found
**Error**: "Could not extract playlist ID"
**Solution**:
1. Ensure the playlist URL is public (not private)
2. Try copying the URL again
3. Use the full URL format: `https://open.spotify.com/playlist/ID`

### No Spotify Tab in Settings

#### Problem: Missing Spotify Integration
**Solution**:
1. Update to DeeMusic v1.0.3 or newer
2. Install required dependencies: `pip install spotipy>=2.22.1`
3. Restart the application

### Low Match Rates

#### Problem: Many tracks not found
**Common Causes**:
- Regional availability differences between Spotify and Deezer
- Very new or obscure tracks
- Different naming conventions

**Solutions**:
1. Lower the minimum match score to 50%
2. Try searching manually for missing tracks
3. Check if tracks are available in your Deezer region

### Performance Issues

#### Problem: Conversion takes too long
**Solutions**:
1. Convert smaller playlists (under 100 tracks)
2. Close other applications to free up resources
3. Check internet speed and stability

---

## 💡 Tips & Best Practices

### For Best Results
1. **Use public playlists** - Private playlists may have access restrictions
2. **Check your region** - Some tracks may not be available in your country
3. **Verify large playlists** - Review match quality for playlists over 50 tracks
4. **Save credentials securely** - Don't share your Client ID/Secret

### Conversion Optimization
- **Popular music** converts better than obscure tracks
- **Official releases** match better than remixes or covers
- **Mainstream artists** have higher success rates
- **Recent releases** may not be available on both platforms yet

### Download Management
- Use the **queue system** to manage large playlist downloads
- **Monitor disk space** before converting large playlists
- **Check audio quality settings** before starting downloads

---

## 🆘 Getting Help

### Support Resources
- **GitHub Issues**: [Report bugs or request features](https://github.com/IAmAnonUser/DeeMusic/issues)
- **Documentation**: Check other `.md` files in the `docs/` folder
- **Community**: Join discussions in the project repository

### When Reporting Issues
Please include:
1. **DeeMusic version**
2. **Error message** (exact text)
3. **Playlist URL** (if public) or playlist size
4. **Your region/country**
5. **Steps to reproduce** the problem

---

## 🔄 Updates & Compatibility

### Version Compatibility
- **DeeMusic v1.0.3+**: Full Spotify integration
- **Earlier versions**: Spotify conversion not available

### Future Enhancements
Planned features include:
- **Apple Music playlist support**
- **YouTube Music playlist support**
- **Improved matching algorithms**
- **Batch playlist conversion**
- **Custom matching rules**

---

**Enjoy converting your Spotify playlists with DeeMusic!** 🎵

*For technical support or feature requests, please visit the [DeeMusic GitHub repository](https://github.com/IAmAnonUser/DeeMusic).* 