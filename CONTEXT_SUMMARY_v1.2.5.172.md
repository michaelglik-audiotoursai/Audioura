# AudioTours Context Summary - v1.2.5.172

## **Current State**
- **Version**: 1.2.5+172 (Git tag: v1.2.5.172)
- **Status**: All changes committed and tagged
- **Location**: `c:\Users\micha\eclipse-workspace\AudioTours\development\`

## **Key Files Modified**
- `audio_tour_app/lib/screens/home_screen.dart` - Tour search & download dialog fixes
- `audio_tour_app/pubspec.yaml` - Version 1.2.5+172
- `map_delivery/app.py` - Added `/search-tours` endpoint
- `newsletter_processor_service.py` - Newsletter API v2 support

## **Recent Major Fixes**
1. **Tour Search Download Issue** - Fixed dialog context problem causing stuck "Downloading..." dialog
2. **Newsletter API v2** - Uses newsletter_id instead of URL, shows dates & article counts
3. **Backend Search Endpoint** - Added `/search-tours` to map_delivery service
4. **Debug Logging** - Comprehensive logging for troubleshooting

## **Known Issues Still Pending**
1. **Tour download dialog context** - Widget unmounting during save operation (logs show `mounted: false`)
2. **Black screen on dismiss** - Navigation issue when user dismisses download dialog
3. **Newsletter delete bug** - Delete doesn't work when filters are applied
4. **Multiple tour audio** - Manual POI selection plays multiple audio simultaneously

## **Architecture Notes**
- **Flutter App**: `audio_tour_app/` - Mobile app (Android/iOS)
- **Backend Services**: Docker containers on `192.168.1.20`
- **Map Service**: Port 5005 - Tour data & downloads
- **Newsletter Service**: Port 5017 - Newsletter processing
- **Database**: PostgreSQL in Docker

## **Development Rules**
- **NEVER prevent user navigation** - Users must be free to navigate
- **Always increment build number** for versions (1.2.5+173, 1.2.5+174, etc.)
- **Test on mobile device** - Version 1.2.5+172 installed
- **Use development workflow** - Modify locally, copy to containers, restart

## **Next Steps**
Ready for minor changes and enhancements. Context restored from this summary.