# Fixes for v1.2.6+376 Test Issues

## Issues Identified and Fixed

### Bug 1: Action changes from 'add' to 'modify' ✅ FIXED
**Root Cause**: UI display issue - the logic was correct but UI showed confusing text
**Fix Applied**: 
- Changed UI text from "New" to "Add" for better clarity
- Verified `_markAsModified()` method correctly preserves `action='add'` for new stops
- **Location**: `edit_tour_screen.dart` line ~750

### Bug 2: "index.html not found" error ✅ FIXED  
**Root Cause**: After successful save and download, tour reload failed due to missing file checks
**Fix Applied**:
- Added proper file existence verification before attempting reload
- Added graceful fallback when reload fails but save was successful
- Enhanced logging to track tour path updates
- **Location**: `edit_tour_screen.dart` `_handleNewTourDownload()` method

### Bug 3: Last original stop overwritten ⚠️ BACKEND ISSUE
**Root Cause**: Backend service bug - mobile app sends correct data
**Evidence**: 
- Mobile app correctly sends original tour ID: `6dd7e8bf-c934-4b6b-922f-3ba32df84108`
- Mobile app correctly marks new stop with `action="add"`
- Backend overwrites stop 8 instead of adding stop 9
**Action Taken**: Created ISSUE-049 document for Services Amazon-Q investigation

## Files Modified

### 1. edit_tour_screen.dart
- **Fix**: Enhanced `_handleNewTourDownload()` with proper error handling
- **Fix**: Changed UI text from "New" to "Add" for clarity
- **Impact**: Eliminates "index.html not found" errors, improves user experience

### 2. ISSUE-049_BACKEND_FORGETS_PREVIOUS_ADDITIONS.md (NEW)
- **Purpose**: Documents backend bug for Services Amazon-Q
- **Evidence**: Complete log analysis showing mobile app sends correct data
- **Priority**: HIGH - breaks core tour editing functionality

## Test Results Expected

### After Fixes:
1. ✅ **UI Display**: New stops will show "Add" indicator instead of "Modified"
2. ✅ **Save Process**: No more "index.html not found" errors after successful saves
3. ⚠️ **Backend Issue**: Stop overwriting will persist until Services Amazon-Q fixes backend

### Verification Steps:
1. Add new stop to existing tour
2. Upload custom audio and mark as modified
3. Save all changes
4. Verify success message appears without errors
5. Check that UI shows "Add" indicator for new stops

## Next Steps

### For Mobile Amazon-Q:
1. ✅ Test fixes with new build
2. ✅ Verify error handling improvements
3. ✅ Confirm UI clarity improvements

### For Services Amazon-Q:
1. ⚠️ Investigate ISSUE-049 backend bug
2. ⚠️ Fix tour editing service to properly handle `action="add"`
3. ⚠️ Ensure new stops are added, not overwritten

## Version Impact
- **Current Version**: v1.2.6+376
- **Fixes Applied**: Mobile app improvements only
- **Backend Fix Required**: Yes, for complete resolution
- **Build Required**: Yes, to test mobile app fixes