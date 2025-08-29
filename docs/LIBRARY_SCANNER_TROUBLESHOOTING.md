# Library Scanner Troubleshooting Guide

## Common Issues and Solutions

### 🔍 Comparison Issues

#### Problem: "Music" or Drive Letters Appearing as Artists
**Symptoms:**
- Comparison results show "Music" or "G:\" as artist names
- Invalid folder names appear in artist list

**Solution (Fixed in v1.0.6):**
- The comparison engine now automatically filters out path-like artists
- Uses clean metadata directly from scan_results.json
- Validates artist names to prevent folder names from appearing

**Technical Details:**
```python
# Path filtering in _convert_tracks_to_albums()
if '\\' in album_artist or '/' in album_artist or ':' in album_artist:
    logger.warning(f"Skipping track with path-like artist '{album_artist}'")
    continue
```

#### Problem: Comparison Button Does Nothing
**Symptoms:**
- Click "Compare with Deezer" but nothing happens
- No error messages or progress indicators

**Troubleshooting Steps:**
1. **Check ARL Token**: Ensure Deezer ARL token is configured in Settings
2. **Verify Scan Data**: Make sure library scan has been completed
3. **Check Library Paths**: Ensure library paths are configured
4. **Review Logs**: Check `%AppData%\DeeMusic\logs\` for error messages

**Common Causes:**
- Empty `self.local_albums` due to scan data not loading
- Missing or invalid Deezer ARL token
- Scan results in wrong format (files vs albums)

#### Problem: No Albums Found After Scan
**Symptoms:**
- Scan completes successfully but comparison finds 0 albums
- "Loaded 0 files into local_albums" in logs

**Solution:**
- Fixed in v1.0.6 with correct scan results key mapping
- Scan worker now uses "scanned_files" key instead of "files"
- Scan completion handlers properly load results into memory

### 📁 Scanning Issues

#### Problem: Scan Results Not Loading
**Symptoms:**
- Previous scan results don't appear after restart
- Status shows "Ready to scan" instead of loaded results

**Troubleshooting:**
1. **Check File Location**: Verify `%AppData%\DeeMusic\scan_results.json` exists
2. **Validate JSON Format**: Ensure scan results file is valid JSON
3. **Review File Permissions**: Check read permissions on AppData directory

**Expected JSON Structure:**
```json
{
  "scan_timestamp": "2025-07-20T09:23:52",
  "total_files": 24,
  "files": [
    {
      "path": "G:\\Music\\Artist\\Album\\Track.mp3",
      "artist": "Artist Name",
      "album": "Album Name",
      "album_artist": "Artist Name",
      "title": "Track Title"
    }
  ]
}
```

#### Problem: Slow Scanning Performance
**Symptoms:**
- Scanning takes very long time
- UI becomes unresponsive during scan

**Solutions:**
- Use incremental scanning for large libraries
- Enable folder modification time tracking
- Scan runs in background thread (should not block UI)

### 🔄 Data Processing Issues

#### Problem: Duplicate Artists in Results
**Symptoms:**
- Same artist appears multiple times with different spellings
- Inconsistent artist names from metadata

**Technical Solution:**
- Enhanced data cleaning in `_convert_tracks_to_albums()`
- Uses `album_artist` field preferentially over `artist`
- Validates and normalizes artist names

#### Problem: Missing Albums Not Detected
**Symptoms:**
- Comparison completes but shows no missing albums
- Known missing albums don't appear in results

**Troubleshooting:**
1. **Check Artist Matching**: Verify artist names match between local and Deezer
2. **Review Fuzzy Matching**: Check album title similarity thresholds
3. **Validate Metadata**: Ensure local files have proper artist/album tags

### 🛠️ Technical Debugging

#### Enable Debug Logging
Add to your configuration or run with debug flags:
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

#### Key Log Messages to Look For
- `"Reloading scan results into local_albums..."`
- `"Loaded X files into local_albums"`
- `"Converting track-level scan data to album format"`
- `"Skipping track with path-like artist"`

#### Common Error Patterns
```
ERROR: results.get("files", []) returns empty list
→ Solution: Fixed in v1.0.6 with correct "scanned_files" key

WARNING: Found 'Music' as artist for path: ...
→ Solution: Path filtering now prevents this

INFO: Local albums count: 0
→ Solution: Scan completion handlers now load results properly
```

### 📊 Performance Optimization

#### Large Library Scanning
- **Incremental Scans**: Only scan modified folders
- **Folder Tracking**: Uses `folder_mtimes.json` for change detection
- **Multi-threading**: Parallel processing for large libraries

#### Memory Management
- **Lazy Loading**: Results loaded only when needed
- **Data Cleanup**: Proper cleanup of scan workers and threads
- **Cache Management**: Efficient handling of comparison results

### 🔧 Configuration Issues

#### Library Paths Not Saving
**Check Configuration File:**
```json
{
  "library_scanner": {
    "library_paths": ["C:\\Music\\", "D:\\Audio\\"]
  }
}
```

#### Comparison Thresholds
**Adjust Matching Sensitivity:**
```json
{
  "library_scanner": {
    "track_match_threshold": 80,
    "album_match_threshold": 75
  }
}
```

## Version-Specific Fixes

### v1.0.6 Improvements
- ✅ Fixed comparison engine data processing
- ✅ Added path filtering for invalid artists
- ✅ Corrected scan results key mapping
- ✅ Enhanced data integrity validation
- ✅ Improved error handling and logging

### Known Limitations
- Requires valid Deezer ARL token for comparison
- Large libraries (>10,000 tracks) may take time to process
- Fuzzy matching may occasionally miss exact matches

## Getting Help

### Log File Locations
- **Main Log**: `%AppData%\DeeMusic\logs\deemusic.log`
- **Debug Logs**: Enable debug logging for detailed information

### Reporting Issues
When reporting Library Scanner issues, please include:
1. **Version**: DeeMusic version number
2. **Library Size**: Approximate number of tracks/albums
3. **Error Messages**: Any error messages from logs
4. **Steps to Reproduce**: Exact steps that cause the issue
5. **Configuration**: Relevant settings (without sensitive data)

### Support Resources
- **Documentation**: Check `docs/` folder for detailed guides
- **Changelog**: Review `CHANGELOG.md` for recent fixes
- **Technical Docs**: See `TECHNICAL_DOCUMENTATION.md` for architecture details