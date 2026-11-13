// [LOCAL-908] The player's "what is playing" panel and the "On the way" sheet.
//
// At every moment the listener can read one of four things:
//   stop      "Stop 3 of 8 · <title>"
//   topic     "On the way to Stop 4 · ~25 min"  +  "Now: <title> · 12 min · <theme>"  [Optional]
//   countdown "On the way to Stop 4 · ~25 min"  +  "Next: <title> — Skip"
//   quiet     "On the way to Stop 4 · quiet"    +  [Play a topic]
//
// Topics use a different colour and an "Optional" badge so they are never taken
// for a stop. Targets are large (>= 56 dp) for use while driving.
library on_the_way_panel;

import 'package:flutter/material.dart';

import '../services/fillings_model.dart';
import '../services/on_the_way_controller.dart';

const Color kOtwStopColor = Color(0xFF2C3E50);
const Color kOtwWayColor = Color(0xFF0E6B5C);
const Color kOtwTopicBg = Color(0xFFFFF3D6);
const Color kOtwBadge = Color(0xFFE08A00);

const Key kOtwPanelKey = ValueKey('otw_panel');
const Key kOtwHeadlineKey = ValueKey('otw_headline');
const Key kOtwNowKey = ValueKey('otw_now');
const Key kOtwOptionalBadgeKey = ValueKey('otw_optional_badge');
const Key kOtwCreditKey = ValueKey('otw_credit');
const Key kOtwSourcesKey = ValueKey('otw_sources');
const Key kOtwSkipKey = ValueKey('otw_skip');
const Key kOtwPlayTopicKey = ValueKey('otw_play_topic');
const Key kOtwMenuKey = ValueKey('otw_menu_button');
const Key kOtwResumeKey = ValueKey('otw_resume');
const Key kOtwEnglishKey = ValueKey('otw_english_notice');
const Key kOtwArrivingKey = ValueKey('otw_arriving');
const Key kOtwQuietKey = ValueKey('otw_quiet');
const Key kOtwAutoPlayKey = ValueKey('otw_setting_autoplay');
const Key kOtwAlwaysQuietKey = ValueKey('otw_setting_always_quiet');
const Key kOtwEnglishSettingKey = ValueKey('otw_setting_english');

/// The headline for the current state (also used for the lock-screen text).
String otwHeadline(OnTheWayController c) {
  if (c.mode == OtwMode.stop) {
    final n = c.stopNumber;
    final total = c.totalStops;
    final title = c.stopTitle?.call(c.currentStop)?.trim() ?? '';
    final base = total != null && total > 0 ? 'Stop $n of $total' : 'Stop $n';
    return title.isEmpty ? base : '$base · $title';
  }
  final head = 'On the way to Stop ${c.nextStopNumber}';
  if (c.mode == OtwMode.quiet) return '$head · quiet';
  final l = c.leg;
  return l == null ? head : '$head · ${l.minutesLabel}';
}

/// "Now: <title> · 12 min · History".
String otwNowLine(FillingItem it) {
  final parts = <String>['${it.minutesLabel} min'];
  if (it.themeLabel.isNotEmpty) parts.add(it.themeLabel);
  return '${it.title} · ${parts.join(' · ')}';
}

class OnTheWayPanel extends StatelessWidget {
  final OnTheWayController controller;
  final VoidCallback onOpenMenu;
  final void Function(String url)? onOpenSources;

  const OnTheWayPanel({
    super.key,
    required this.controller,
    required this.onOpenMenu,
    this.onOpenSources,
  });

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        // No fillings (an old tour) or "always quiet": nothing is added to the
        // player — it looks and works exactly as before.
        if (!controller.active) return const SizedBox.shrink();
        final stop = controller.mode == OtwMode.stop;
        return Material(
          key: kOtwPanelKey,
          color: stop ? kOtwStopColor : kOtwWayColor,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
                child: Row(
                  children: [
                    Icon(stop ? Icons.place : Icons.directions_car,
                        color: Colors.white, size: 22),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        otwHeadline(controller),
                        key: kOtwHeadlineKey,
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w600),
                      ),
                    ),
                    if (stop && controller.leg != null)
                      TextButton(
                        key: kOtwMenuKey,
                        onPressed: onOpenMenu,
                        child: const Text('Topics',
                            style: TextStyle(color: Colors.white)),
                      ),
                  ],
                ),
              ),
              if (!stop) _body(context),
            ],
          ),
        );
      },
    );
  }

  Widget _body(BuildContext context) {
    final c = controller;
    final it = c.item;
    final children = <Widget>[];

    if (c.mode == OtwMode.topic && it != null) {
      children.add(_topicCard(context, it, now: true));
    } else if (c.mode == OtwMode.countdown && it != null) {
      children.add(_topicCard(context, it, now: false));
    } else if (c.mode == OtwMode.quiet) {
      children.add(Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
        child: Row(children: [
          Expanded(
            child: SizedBox(
              height: 56,
              child: ElevatedButton.icon(
                key: kOtwPlayTopicKey,
                onPressed: c.playTopic,
                icon: const Icon(Icons.play_arrow, size: 28),
                label: const Text('Play a topic',
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
                style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: kOtwWayColor),
              ),
            ),
          ),
          const SizedBox(width: 8),
          _menuButton(),
        ]),
      ));
    }

    final resume = c.resume;
    if (resume != null) {
      children.add(Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
        child: SizedBox(
          height: 48,
          child: OutlinedButton.icon(
            key: kOtwResumeKey,
            onPressed: c.resumeLater,
            icon: const Icon(Icons.replay, color: Colors.white),
            label: Text('Resume ${resume.item.title} later',
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white)),
            style: OutlinedButton.styleFrom(
                side: const BorderSide(color: Colors.white70)),
          ),
        ),
      ));
    }

    if (c.englishOnlyNotice) {
      children.add(const Padding(
        padding: EdgeInsets.fromLTRB(14, 0, 14, 8),
        child: Text('Topics available in English',
            key: kOtwEnglishKey,
            style: TextStyle(color: Colors.white70, fontSize: 12.5)),
      ));
    }
    return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children);
  }

  Widget _menuButton() => SizedBox(
        height: 56,
        width: 56,
        child: IconButton(
          key: kOtwMenuKey,
          tooltip: 'On the way: choose a topic',
          onPressed: onOpenMenu,
          icon: const Icon(Icons.list, color: Colors.white, size: 28),
        ),
      );

  Widget _topicCard(BuildContext context, FillingItem it, {required bool now}) {
    final c = controller;
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 10),
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
      decoration: BoxDecoration(
        color: kOtwTopicBg,
        borderRadius: BorderRadius.circular(10),
        border: const Border(left: BorderSide(color: kOtwBadge, width: 5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                key: kOtwOptionalBadgeKey,
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                    color: kOtwBadge, borderRadius: BorderRadius.circular(10)),
                child: const Text('Optional',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w700)),
              ),
              if (c.arriving) ...[
                const SizedBox(width: 8),
                const Text('Arriving…',
                    key: kOtwArrivingKey,
                    style: TextStyle(fontSize: 12.5, color: Color(0xFF6B4A00))),
              ],
            ],
          ),
          const SizedBox(height: 6),
          if (now)
            Text('Now: ${otwNowLine(it)}',
                key: kOtwNowKey,
                style: const TextStyle(
                    color: Color(0xFF3B2A00),
                    fontSize: 16,
                    fontWeight: FontWeight.w600))
          else
            Text('Next: ${it.title} — Skip',
                key: kOtwNowKey,
                style: const TextStyle(
                    color: Color(0xFF3B2A00),
                    fontSize: 16,
                    fontWeight: FontWeight.w600)),
          if (!now)
            Text('Starts in ${c.countdownLeft} s',
                style: const TextStyle(color: Color(0xFF6B4A00), fontSize: 13)),
          if (now && it.creditLine.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(it.creditLine,
                key: kOtwCreditKey,
                style: const TextStyle(color: Color(0xFF6B4A00), fontSize: 11.5)),
          ],
          if (now && it.sourcesUrl != null && onOpenSources != null)
            Align(
              alignment: Alignment.centerLeft,
              child: InkWell(
                key: kOtwSourcesKey,
                onTap: () => onOpenSources!(it.sourcesUrl!),
                child: const Padding(
                  padding: EdgeInsets.symmetric(vertical: 4),
                  child: Text('Sources',
                      style: TextStyle(
                          color: Color(0xFF0B57D0),
                          fontSize: 12.5,
                          decoration: TextDecoration.underline)),
                ),
              ),
            ),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(
              child: SizedBox(
                height: 56,
                child: ElevatedButton.icon(
                  key: kOtwSkipKey,
                  onPressed: c.skip,
                  icon: const Icon(Icons.skip_next, size: 28),
                  label: const Text('Skip',
                      style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
                  style: ElevatedButton.styleFrom(
                      backgroundColor: kOtwBadge,
                      foregroundColor: Colors.white),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              decoration: BoxDecoration(
                  color: kOtwWayColor, borderRadius: BorderRadius.circular(28)),
              child: _menuButton(),
            ),
          ]),
        ],
      ),
    );
  }
}

/// Open the "On the way" sheet.
Future<void> showOnTheWaySheet(BuildContext context, OnTheWayController c) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
    builder: (ctx) => OnTheWaySheet(controller: c),
  );
}

class OnTheWaySheet extends StatelessWidget {
  final OnTheWayController controller;
  const OnTheWaySheet({super.key, required this.controller});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListenableBuilder(
        listenable: Listenable.merge([controller, controller.settings]),
        builder: (context, _) {
          final c = controller;
          final l = c.leg;
          final onTheWay = c.mode != OtwMode.stop;
          return SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 14, 8, 16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Text(
                      l == null
                          ? 'On the way'
                          : 'On the way to Stop ${l.afterStop + 1} · ${l.minutesLabel}',
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                  ),
                  if (!onTheWay)
                    const Padding(
                      padding: EdgeInsets.fromLTRB(12, 4, 12, 4),
                      child: Text('Topics play after this stop.',
                          style: TextStyle(color: Colors.black54)),
                    ),
                  if (c.resume != null && onTheWay)
                    ListTile(
                      key: kOtwResumeKey,
                      leading: const Icon(Icons.replay),
                      title: Text('Resume ${c.resume!.item.title} later'),
                      onTap: () {
                        c.resumeLater();
                        Navigator.of(context).maybePop();
                      },
                    ),
                  if (l != null)
                    for (var i = 0; i < l.items.length; i++)
                      _row(context, c, l.items[i], i),
                  if (onTheWay)
                    ListTile(
                      key: kOtwQuietKey,
                      minVerticalPadding: 14,
                      leading: const Icon(Icons.volume_off, size: 28),
                      title: const Text('Quiet',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w600)),
                      subtitle: const Text('No topics until the next stop'),
                      trailing: c.mode == OtwMode.quiet
                          ? const Icon(Icons.check)
                          : null,
                      onTap: () {
                        c.chooseQuiet();
                        Navigator.of(context).maybePop();
                      },
                    ),
                  const Divider(),
                  SwitchListTile(
                    key: kOtwAutoPlayKey,
                    title: const Text('Auto-play topics after a stop'),
                    value: c.settings.autoPlay,
                    onChanged: (v) => c.settings.setAutoPlay(v),
                  ),
                  SwitchListTile(
                    key: kOtwAlwaysQuietKey,
                    title: const Text('Always quiet (topics off)'),
                    value: c.settings.alwaysQuiet,
                    onChanged: (v) => c.settings.setAlwaysQuiet(v),
                  ),
                  SwitchListTile(
                    key: kOtwEnglishSettingKey,
                    title: const Text('Show topics that are only in English'),
                    subtitle: const Text('Off: hidden when your tour is translated'),
                    value: c.settings.showEnglishNotice,
                    onChanged: (v) => c.settings.setShowEnglishNotice(v),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _row(BuildContext context, OnTheWayController c, FillingItem it, int i) {
    final playing = c.mode == OtwMode.topic && c.itemIndex == i;
    final canPlay = c.mode != OtwMode.stop;
    return ListTile(
      key: ValueKey('otw_row_$i'),
      minVerticalPadding: 10,
      title: Text(it.title,
          style: TextStyle(
              fontSize: 15.5,
              fontWeight: playing ? FontWeight.w700 : FontWeight.w500)),
      subtitle: Text(
          '${it.minutesLabel} min${it.themeLabel.isEmpty ? '' : ' · ${it.themeLabel}'}'
          '${playing ? ' · playing' : ''}'),
      trailing: canPlay
          ? IconButton(
              key: ValueKey('otw_play_$i'),
              iconSize: 36,
              tooltip: 'Play ${it.title}',
              icon: const Icon(Icons.play_circle_fill, color: kOtwWayColor),
              onPressed: () {
                c.choose(i);
                Navigator.of(context).maybePop();
              },
            )
          : null,
    );
  }
}
