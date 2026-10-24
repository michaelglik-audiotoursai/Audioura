// [LOCAL-760 / D708 / D709] The user-facing wording for organiser-audio
// ("broadcast") tours — Edit/Translate disabled notices and the translation
// failure message — in ONE pure place so my_tours_screen and home_screen cannot
// drift and a golden test pins every string.
//
// Michael (2026-10-24, both phones):
//   * Edit/Translate were still offered on an organiser-audio tour; pressing
//     Edit let the user work for a long time, then Save failed with "This tour
//     is maintained on the organiser's own site…". The menu items must be
//     DISABLED with an ⓘ that says so up front (never open the edit screen).
//   * Translate showed "Translation Not Available. Russian wasn't available for
//     this older tour, so the English version was saved" — misleading for a
//     server 403 translation_not_offered. That case must say the broadcast /
//     D708 reason; the "older tour" wording stays for the case it was written
//     for.
//
// PURE: no BuildContext, no I/O — strings in, strings out.
library;

/// The ⓘ text when Edit is tapped on a disabled organiser-audio tour.
///
/// A broadcast tour's audio is the organiser's, hosted on their own site; it is
/// never edited through our voice pipeline (the server also refuses it, 409
/// organiser_audio_not_editable). The OWNER is additionally pointed at the
/// builder on the community page ("Make a tour from your own audio"); a member
/// is not (they cannot change it at all).
String editDisabledNotice({required bool isOwner}) {
  const base =
      'Editing is not available for broadcast tours. This tour is maintained on '
      "the organiser's own site; the organiser updates it there.";
  if (isOwner) {
    return '$base Change it in "Make a tour from your own audio" on the '
        'community page.';
  }
  return base;
}

/// The ⓘ text when Translate is tapped on a disabled organiser-audio tour
/// (D708: the audio belongs to the organiser — Audioura never had the text to
/// translate and never stored the audio to re-synthesize).
String translateDisabledNotice() {
  return 'Translation is not available for broadcast tours: the audio belongs '
      'to the organiser (D708).';
}

/// The dialog body shown when a translation request FAILED.
///
/// [translationNotOffered] is true when the server refused with 403
/// translation_not_offered (an organiser-audio / broadcast tour) — then the
/// D708 broadcast wording is shown, NOT the misleading "older tour" line.
/// Otherwise the original per-language fallback wording is kept, naming the
/// languages that were not available ([failedLanguageNames], e.g. "Russian, …").
String translationFailureMessage({
  required bool translationNotOffered,
  required String failedLanguageNames,
}) {
  if (translationNotOffered) {
    return translateDisabledNotice();
  }
  return "$failedLanguageNames wasn't available for this older tour, so the "
      'English version was saved.';
}
