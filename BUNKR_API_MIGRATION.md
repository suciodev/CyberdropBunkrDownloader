# Bunkr Download Script Debugging Notes

## Problem Statement
The CyberdropBunkrDownloaderCustom script is failing to download files from bunkr.cr albums due to API changes. The script uses an old encryption-based flow that no longer works.

**Error:**
- HTTP 404 when POSTing to `/api/vs` with a slug to fetch encryption data
- Original error: `TypeError: 'NoneType' object is not subscriptable` when trying to decrypt

## Discovery Timeline

### 1. Initial API Endpoint (DEPRECATED)
- **Endpoint:** `https://bunkr.cr/api/vs`
- **Method:** POST
- **Payload:** `{"slug": "BEnwwXeFncR4b"}`
- **Status:** Returns 404 HTML page ("Resource not found") even though the file exists
- **Reason:** API endpoint no longer supports this flow or requires additional authentication

### 2. New CDN Signing Flow (CURRENT)
The site now uses a different approach:

#### Step 1: Get File Page
- **URL:** `https://bunkr.cr/f/{slug}` (e.g., `https://bunkr.cr/f/BEnwwXeFncR4b`)
- **Status:** 200 OK — file page loads successfully
- **Extract:** Original filename from `<div class="theItem" title="...">` or `<p class="theName">`
- **Example:** `My movie 6_23.mp4`

#### Step 2: Sign CDN Request
- **Endpoint:** `https://glb-apisign.cdn.cr/sign`
- **Method:** POST
- **Headers:**
  - `Content-Type: application/json`
  - `Origin: https://bunkr.cr`
  - `Referer: https://bunkr.cr/f/{slug}`
- **Payload:** `{"path": "/storage/media/My-movie-6_23.mp4"}`
- **Response:** 
  ```json
  {
    "ex": 1780390103,
    "token": "228c8b02ca91183c0e4f22441a9211e928a8913a"
  }
  ```
- **Success Condition:** Returns `ex` (expiry timestamp) and `token` (signed request token)

#### Step 3: Download from CDN
- **URL:** `https://glb-cdn.cdn.cr/storage/media/{filename}?ex={ex}&token={token}`
- **Status:** Uses signed URL with expiry
- **Note:** Token is ephemeral; request must happen before expiry timestamp

### 3. File Page HTML Structure
The file page contains the filename in multiple places:
- `<div class="theItem" title="My movie 6_23.mp4">` — title attribute
- `<p class="theName">My movie 6_23.mp4</p>` — visible filename text
- `<p style="display:none;">My movie 6_23.mp4</p>` — hidden paragraph
- Thumbnail path: `https://static.scdn.st/{id}/thumbs/My-movie-6_23-{HASH}.png`

**Current Issue:** Script is extracting `v-2.3.11` (a footer version string) instead of the actual filename. Need to:
1. Find the `theItem` div first
2. Extract filename only from within that div
3. Ignore global `<p>` tags that may contain unrelated content

## Changes Made to dump.py

### 1. Updated Constants
```python
BUNKR_SIGN_API_URL = "https://glb-apisign.cdn.cr/sign"
```

### 2. New Function: `get_signed_download_url()`
- Takes: file path like `"storage/media/filename.mp4"`, file page URL, session
- POSTs to `/sign` endpoint with proper headers
- Returns: Signed CDN URL with `ex` and `token` parameters
- Handles errors and returns None on failure

### 3. Updated `create_session()`
- Changed Referer from `https://bunkr.sk/` to `https://bunkr.cr/`
- Maintains User-Agent for browser compatibility

### 4. Updated `get_real_download_url()` (INCOMPLETE)
- Now attempts to use new CDN signing flow
- Extracts filename from file page using BeautifulSoup
- **BUG:** Filename extraction still returning wrong results
- Falls back to legacy encryption method if signing fails

## Current Status

### What Works
✅ Can reach album pages and get file page URLs  
✅ Can POST to `/sign` API and get valid tokens (when given correct path)  
✅ Domain migration from bunkr.sk to bunkr.cr handled  
✅ Session headers with proper Origin/Referer set  

### What Doesn't Work
❌ Filename extraction from file page (gets `v-2.3.11` instead of actual filename)  
❌ Subsequent signing API call fails with wrong filename  
❌ Legacy encryption fallback doesn't work (API endpoint deprecated)  

### Test Case
- Album: `https://bunkr.cr/a/XUZpfGv4` (contains 1 file: "My movie 6_23.mp4")
- File: `https://bunkr.cr/f/BEnwwXeFncR4b`
- File ID: `35728942` (extracted from page, used by `/api/lv` tracker)

## Next Steps

### Immediate (Required for Fix)
1. **Fix filename extraction** in `get_real_download_url()`:
   - Locate `<div class="theItem">` first
   - Extract `title` attribute OR `<p class="theName">` from WITHIN that div only
   - Ignore other `<p>` tags on the page (e.g., footer version info)
   - Add debug output to verify extracted filename before using it

2. **Test the extraction** with actual file page:
   - Print extracted filename to verify it's `My movie 6_23.mp4`
   - Verify the signed CDN URL works by testing download

### Secondary (Enhancement)
3. **Handle multiple files in albums**:
   - Current code only handles single-file albums via "direct_link" flag
   - For albums with multiple files, need to iterate through all `/f/` links
   - Extract and sign each one separately

4. **Add retry logic** for sign API:
   - Some requests may fail transiently
   - Implement exponential backoff or retry on timeout

5. **Cache tokens** if downloading multiple files from same album:
   - Tokens are valid for duration of `ex` timestamp
   - Could reuse token for same file path

## Code Notes

### File Path Format
The file path for the sign API must be:
- **Correct:** `/storage/media/My movie 6_23.mp4`
- **With spaces:** Path can contain spaces (verified working)
- **With dashes:** `/storage/media/My-movie-6_23.mp4` (also works)

### Session Reuse
The `session` object in `get_encryption_data()` refers to the global session created in `__main__`. This is fine for headers and cookies, but consider passing session as parameter to avoid global state.

### Legacy Code to Remove (Eventually)
- `get_encryption_data()` function (old API endpoint)
- `decrypt_encrypted_url()` function (XOR decryption)
- `BUNKR_VS_API_URL_FOR_SLUG` constant
- All references to "slug" in new code flow

These were used for the old `/api/vs` encryption method and are no longer needed once CDN signing is fully implemented.

## Testing Commands

```bash
# Test album download
python -u dump.py -u "https://bunkr.cr/a/XUZpfGv4" -w

# Check for extracted filename in output (look for DEBUG lines)
# Should show: [DEBUG] Extracted filename: 'My movie 6_23.mp4'
# Should show: [DEBUG] Trying file_path: storage/media/My-movie-6_23.mp4
# Should show: [+] File list exported in downloads\Jilissa\url_list.txt

# Verify URL in url_list.txt
cat downloads\Jilissa\url_list.txt
# Should contain: https://glb-cdn.cdn.cr/storage/media/My-movie-6_23.mp4?ex=...&token=...
```

## References
- Album URL structure: `https://bunkr.cr/a/{albumId}` or `https://bunkr.cr/a/{slug}`
- File URL structure: `https://bunkr.cr/f/{fileSlug}`
- CDN sign endpoint: `https://glb-apisign.cdn.cr/sign`
- CDN download endpoint: `https://glb-cdn.cdn.cr/{filepath}?ex={timestamp}&token={hash}`

## Known Limitations
1. **Cloudflare DDoS protection:** Some requests may be blocked or throttled
2. **Token expiry:** Signed URLs are only valid for a limited time
3. **File removal:** Files can be removed by uploader; no way to detect until API call fails
4. **Album structure:** Script assumes albums have single or direct link mode; may not handle all album types
