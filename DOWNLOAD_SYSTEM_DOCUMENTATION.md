# DeeMusic Download System - Technical Documentation

## Overview

The DeeMusic application downloads encrypted audio files from Deezer's CDN and decrypts them locally using a sophisticated Blowfish CBC encryption system. This document explains the complete flow from user request to final playable audio file.

## 1. Authentication & API Access

### ARL (Authentication Token)
- **Purpose**: Authenticates with Deezer's private API
- **Format**: 192-character hexadecimal string
- **Storage**: `settings.json` under `deezer.arl`
- **Usage**: Set as cookie `arl` for all private API requests

### API Tokens
- **License Token**: Used for media URL requests (`AAAAAmg6Bu...`)
- **API Token**: Session-based token for private API calls, refreshed automatically
- **CSRF Protection**: Tokens expire and require refresh via `deezer.getUserData`

## 2. Download Flow Architecture

```
User Request → Track Info Fetch → Media URL Request → Download → Decrypt → Apply Metadata → Save
```

### 2.1 Track Information Gathering
```python
# Method: get_track_details_sync_private()
POST /ajax/gw-light.php?method=deezer.pageTrack
```

**Critical Data Retrieved:**
- `SNG_ID`: Track identifier for decryption key
- `TRACK_TOKEN`: Required for media URL acquisition
- `MD5_ORIGIN`: File integrity verification
- `FILESIZES`: Available quality options (MP3_320, FLAC, etc.)
- `ALB_PICTURE`/`ART_PICTURE`: Artwork identifiers

### 2.2 Media URL Acquisition
```python
# Method: get_track_download_url_sync()
POST https://media.deezer.com/v1/get_url
```

**Payload:**
```json
{
    "license_token": "AAAAAmg6Bu...",
    "media": [{
        "type": "FULL",
        "formats": [{"cipher": "BF_CBC_STRIPE", "format": "MP3_320"}]
    }],
    "track_tokens": ["AAAAAWg6By..."]
}
```

**Response Contains:**
- Encrypted file download URL
- Cipher type confirmation (`BF_CBC_STRIPE`)
- Temporary access credentials in URL parameters

## 3. Encryption System: Blowfish CBC Stripe

### 3.1 Key Generation Algorithm
The most critical component - **MUST BE EXACT**:

```python
def _generate_decryption_key(self, sng_id_str: str) -> Optional[bytes]:
    bf_secret_str = "g4el58wc0zvf9na1"  # Hardcoded Deezer secret
    
    # Generate MD5 hash of track ID
    hashed_sng_id_hex = MD5.new(sng_id_str.encode('ascii', 'ignore')).hexdigest()
    # Result: 32-character hex string
    
    # XOR algorithm: Combine hash parts with secret
    key_char_list = []
    for i in range(16):
        xor_val = (ord(hashed_sng_id_hex[i]) ^ 
                   ord(hashed_sng_id_hex[i + 16]) ^ 
                   ord(bf_secret_str[i]))
        key_char_list.append(chr(xor_val))
    
    key_string = "".join(key_char_list)
    key_bytes = key_string.encode('utf-8')
    
    # Validate key length (Blowfish requirement: 4-56 bytes)
    if not (4 <= len(key_bytes) <= 56):
        key_bytes = key_string.encode('ascii', 'ignore')
        if not (4 <= len(key_bytes) <= 56):
            return None
    
    return key_bytes
```

**Why This Works:**
- Each track has a unique `SNG_ID`
- The XOR operation with Deezer's secret creates track-specific keys
- The same track always generates the same key

### 3.2 Decryption Process: CBC Stripe Method

```python
def _decrypt_file_bf_cbc_stripe(self, encrypted_path: Path, key: bytes, sng_id: str) -> Optional[Path]:
    iv = bytes.fromhex("0001020304050607")  # Fixed initialization vector
    chunk_size = 2048                       # First chunk size in each segment
    segment_size = chunk_size * 3           # Total segment size (6144 bytes)
```

**Stripe Pattern:**
```
Segment (6144 bytes) = [Encrypted Chunk (2048)] + [Plain Data (4096)]
```

**Algorithm:**
1. **Read Segments**: Process file in 6144-byte segments
2. **Split Each Segment**: 
   - First 2048 bytes: Encrypted with Blowfish CBC
   - Remaining 4096 bytes: Plain data (not encrypted)
3. **Decrypt**: Only the first chunk using `Blowfish.new(key, Blowfish.MODE_CBC, iv)`
4. **Reassemble**: Combine decrypted chunk + plain data
5. **Handle Remainder**: Final partial segment processed appropriately

**Code Flow:**
```python
while True:
    # Read up to segment_size bytes
    chunk_data = f_enc.read(segment_size - len(buffer))
    buffer += chunk_data
    
    while len(buffer) >= segment_size:
        segment = buffer[:segment_size]
        buffer = buffer[segment_size:]
        
        # Split segment
        encrypted_chunk = segment[:chunk_size]      # First 2048 bytes
        plain_remainder = segment[chunk_size:]      # Next 4096 bytes
        
        # Decrypt only the first chunk
        cipher = Blowfish.new(key, Blowfish.MODE_CBC, iv)
        decrypted_chunk = cipher.decrypt(encrypted_chunk)
        
        # Write: decrypted + plain
        f_dec.write(decrypted_chunk + plain_remainder)
```

## 4. File Handling & Paths

### 4.1 Temporary File Management
```python
# Download location
encrypted_temp_path = Path(tempfile.gettempdir()) / f"deemusic_{track_id}_{safe_filename}.encrypted.part"

# Decryption output
decrypted_path = encrypted_temp_path.with_suffix('.decrypted.tmp')

# Final location (based on user settings)
final_path = Path(download_dir) / artist_folder / album_folder / filename
```

### 4.2 Folder Structure Logic
```python
# User settings control structure
folder_conf = config.get_setting('downloads.folder_structure', {})

if folder_conf.get('create_artist_folders', True):
    path_components.append(sanitized_artist_name)

if folder_conf.get('create_album_folders', True):
    path_components.append(sanitized_album_name)

if folder_conf.get('create_cd_folders', True) and total_discs > 1:
    path_components.append(f"CD{disc_number}")
```

## 5. Metadata & Artwork Processing

### 5.1 Audio Metadata (using Mutagen)
```python
# Applied after decryption, before final file move
audio = MP3(decrypted_file_path, ID3=ID3)

# Standard tags
audio.tags.add(TIT2(encoding=3, text=title))        # Title
audio.tags.add(TPE1(encoding=3, text=artist))       # Artist
audio.tags.add(TALB(encoding=3, text=album))        # Album
audio.tags.add(TRCK(encoding=3, text=track_number)) # Track number

# Embedded artwork
if cover_data:
    audio.tags.add(APIC(
        encoding=3,
        mime='image/jpeg',
        type=3,  # Cover (front)
        desc='Cover',
        data=cover_data
    ))

audio.save()
```

### 5.2 Separate Artwork Files
```python
# Album cover: {albumImageTemplate}.{albumImageFormat}
album_cover_path = album_directory / f"{album_template}.{album_format}"

# Artist image: {artistImageTemplate}.{artistImageFormat}  
artist_image_path = artist_directory / f"{artist_template}.{artist_format}"

# Downloaded from:
# Album: https://e-cdns-images.dzcdn.net/images/cover/{hash}/{size}x{size}-000000-80-0-0.jpg
# Artist: https://e-cdns-images.dzcdn.net/images/artist/{hash}/{size}x{size}-000000-80-0-0.jpg
```

## 6. Quality & Format Handling

### 6.1 Available Formats
- **MP3_320**: 320 kbps MP3 (most common)
- **MP3_128**: 128 kbps MP3 (lower quality)
- **FLAC**: Lossless format
- **AAC_64**: 64 kbps AAC (rare)

### 6.2 Quality Selection Logic
```python
quality = config.get_setting('downloads.quality', 'MP3_320')
filesize_key = f'filesize_{quality.lower()}'

if track_info.get(filesize_key, 0) > 0:
    # Requested quality available
    selected_format = quality
else:
    # Fallback to MP3_128 or best available
    selected_format = find_best_available_quality(track_info)
```

## 7. Error Handling & Recovery

### 7.1 Common Failure Points

**Authentication Failures:**
- Invalid ARL → Re-authentication required
- Expired tokens → Automatic refresh via `deezer.getUserData`

**Download Failures:**
- Network timeouts → Retry with exponential backoff
- Invalid URLs → Re-request media URL
- Partial downloads → Resume not supported, restart download

**Decryption Failures:**
- Wrong key → Verify SNG_ID extraction
- Corrupted file → Size mismatch detection
- Invalid segments → Graceful handling of malformed chunks

### 7.2 Validation Steps
```python
# File size verification
actual_decrypted_size = decrypted_path.stat().st_size
actual_encrypted_size = encrypted_path.stat().st_size

if actual_decrypted_size != actual_encrypted_size:
    logger.error("Decryption size mismatch")
    return None

# Audio file validation
try:
    audio = MP3(decrypted_path)
    if audio.info.length <= 0:
        raise Exception("Invalid audio file")
except Exception:
    logger.error("Corrupted audio file detected")
    return None
```

## 8. Security Considerations

### 8.1 Key Management
- **Never log the complete decryption key**
- **Secret string is hardcoded** (reverse-engineered from Deezer clients)
- **Keys are unique per track** - no key reuse between tracks

### 8.2 Network Security
- All requests use HTTPS
- ARL token is sensitive - treat like a password
- Temporary files are cleaned up after processing

## 9. Performance Optimizations

### 9.1 Concurrent Downloads
```python
max_threads = config.get_setting('downloads.concurrent_downloads', 3)
thread_pool.setMaxThreadCount(max_threads)
```

### 9.2 Memory Management
- Streaming decryption (not loading entire file into memory)
- Buffer management for segment processing
- Immediate cleanup of temporary files

## 10. Troubleshooting Guide

### 10.1 Audio Quality Issues
**Symptoms:** Garbled, static, or corrupted audio
**Causes:** 
- Incorrect key generation algorithm
- Wrong IV or cipher parameters
- Segment size misalignment

**Solutions:**
- Verify XOR algorithm matches exactly
- Check hardcoded values (IV, secret, segment sizes)
- Compare with working implementation

### 10.2 Authentication Issues
**Symptoms:** "Invalid CSRF token", "Authentication failed"
**Solutions:**
- Refresh ARL token from browser
- Clear session cookies
- Verify ARL format (192 hex characters)

### 10.3 Download Failures
**Symptoms:** Empty files, network errors, timeout
**Solutions:**
- Check network connectivity
- Verify media URL hasn't expired
- Retry with fresh token request

## 11. Configuration Reference

### 11.1 Critical Settings
```json
{
    "downloads": {
        "quality": "MP3_320",
        "saveArtwork": true,
        "embedArtwork": true,
        "embeddedArtworkSize": 1000,
        "artistArtworkSize": 1200,
        "albumArtworkSize": 1000,
        "concurrent_downloads": 3
    }
}
```

### 11.2 File Naming Templates
```json
{
    "filename_templates": {
        "track": "{artist} - {title}",
        "album_track": "{track_number:02d} - {album_artist} - {title}",
        "playlist_track": "{track_number:02d} - {artist} - {title}"
    }
}
```

## 12. Implementation Notes

### 12.1 Critical Constants
```python
# These values MUST NOT change - they are part of Deezer's protocol
BF_SECRET = "g4el58wc0zvf9na1"           # Blowfish secret key
IV_HEX = "0001020304050607"              # Initialization vector
CHUNK_SIZE = 2048                        # Encrypted chunk size
SEGMENT_SIZE = 6144                      # Total segment size (3 * CHUNK_SIZE)
```

### 12.2 API Endpoints
```python
# Primary endpoints used by the system
TRACK_INFO_URL = "https://www.deezer.com/ajax/gw-light.php?method=deezer.pageTrack"
MEDIA_URL_API = "https://media.deezer.com/v1/get_url"
TOKEN_REFRESH_URL = "https://www.deezer.com/ajax/gw-light.php?method=deezer.getUserData"

# CDN patterns for artwork
ALBUM_ART_CDN = "https://e-cdns-images.dzcdn.net/images/cover/{hash}/{size}x{size}-000000-80-0-0.jpg"
ARTIST_ART_CDN = "https://e-cdns-images.dzcdn.net/images/artist/{hash}/{size}x{size}-000000-80-0-0.jpg"
```

### 12.3 Thread Safety
- Each download worker operates independently
- Shared resources (config, API) are thread-safe
- Temporary files use unique names to prevent conflicts
- Signal emission is thread-safe through Qt's mechanism

---

**Important Note**: This system is based on reverse-engineering of Deezer's encryption. The exact algorithms, secret strings, and parameters must match Deezer's implementation for proper decryption. Any deviation in the key generation or decryption process will result in corrupted audio files.

**Legal Disclaimer**: This documentation is for educational purposes. Users must comply with Deezer's Terms of Service and applicable copyright laws in their jurisdiction.

## Proxy Settings Integration

**Location**: Proxy settings are integrated into the main Settings dialog under the "Network" tab (File > Settings > Network).

**Features**:
- Comprehensive proxy configuration (HTTP, HTTPS, SOCKS4, SOCKS5)
- Built-in connection testing
- Retry failed downloads with proxy option
- Temporary proxy enabling for retries
- Up-to-date proxy service recommendations

**Usage**: When retrying failed downloads, users are prompted with an option to enable proxy temporarily to bypass geo-restrictions. 