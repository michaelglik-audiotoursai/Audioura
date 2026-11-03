// [LOCAL-854] (D757) OpenStreetMap attribution for every flutter_map on the app.
//
// The raster tiles ultimately come from OpenStreetMap data, whether they are
// served by our tile-cache proxy (the new default primary, see MapTiles) or, as
// a last-resort fallback, straight from the OSM CDN. OSM's licence (ODbL)
// requires visible "© OpenStreetMap contributors" attribution wherever those
// tiles are shown. Repointing the app at the proxy does not remove that
// obligation — the underlying data is still OSM — so this widget is added as a
// child of each FlutterMap and the credit stays visible on the map.
//
// Using flutter_map's RichAttributionWidget keeps the credit unobtrusive (a
// small "i" badge that expands to the link) while remaining always present.

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:url_launcher/url_launcher.dart';

/// The standard OSM attribution overlay. Place it LAST in a FlutterMap's
/// `children` so it paints above the tiles and markers.
class OsmAttribution extends StatelessWidget {
  const OsmAttribution({super.key});

  @override
  Widget build(BuildContext context) {
    return RichAttributionWidget(
      // Show the badge so the credit is always reachable on the map.
      showFlutterMapAttribution: false,
      attributions: [
        TextSourceAttribution(
          '© OpenStreetMap contributors',
          onTap: () => launchUrl(
            Uri.parse('https://www.openstreetmap.org/copyright'),
            mode: LaunchMode.externalApplication,
          ),
        ),
      ],
    );
  }
}
