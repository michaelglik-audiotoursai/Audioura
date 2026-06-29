# Website Brief — build www.audioura.com (hand-off for a separate chat)

**Purpose:** a simple, modern, single-page marketing site for the Audioura mobile app. The four required
sections: (1) what Audioura does, (2) how to get it (Apple + Google), (3) free vs. paid, (4) how to connect.
**Source of truth:** this brief (synthesized from Audioura's 3 product decks). Build the page from the copy below.
**Audience:** everyday travelers, museum-goers, commuters, and newsletter readers — consumer tone, not investors.

> Do NOT include any investor/fundraising or development-cost content (one older deck had it). This is a consumer site.

---

## Brand basics
- **Name:** Audioura  (legal: Audioura LLC)
- **Tagline:** *"Audioura — Where stories guide you."*
- **Voice/tone:** warm, effortless, hands-free, on-the-go. Emphasize "listen, don't look."
- **Logo / colors / fonts:** NOT provided — use a clean audio/travel palette as placeholder (e.g. deep indigo +
  warm amber accent, large rounded sans-serif) and leave a clearly-marked slot for the real logo + screenshots.
- **Domain:** www.audioura.com. Also host the existing **privacy policy at /privacy** (file
  `PRIVACY_POLICY.html` already exists — this doubles as the store-required privacy URL). Add a footer link to it.

## Page structure (single scrolling landing page)
1. Header / nav (logo, links: What it does · Pricing · Get it · Contact)
2. Hero (tagline + one-line pitch + store badges)
3. What Audioura does (the 3 modes + voice control + Treats)
4. How to get it (App Store + Google Play)
5. Pricing (Free vs Premium)
6. Contact / Connect
7. Footer (privacy policy link, © Audioura LLC, social)

---

## SECTION 1 — Hero
**Headline:** Where stories guide you.
**Subhead:** Audioura turns the world around you — and the news you care about — into hands-free audio.
Generate a walking tour of any place on earth, or listen to your newsletters and articles, all by voice.
**Primary CTAs:** [Download on the App Store] [Get it on Google Play] (badges; links = placeholders, see §4)
**Visual:** app screenshot / phone mockup (placeholder).

## SECTION 2 — What Audioura does
Intro line: *One simple, voice-first app. Three ways to listen.*

**🎧 Audio Tours**
Personalized audio guidance tailored to your journey and your interests. Audioura adapts in real time for
**walking, biking, driving, and virtual tours** — and works for museums, sculpture parks, and state parks, anywhere
in the world. Each point of interest comes with its history, artistic significance, and location. Navigate entirely
by voice: triple-click your headphone button to jump between stops — never look at your phone.

**📰 Audio News & Newsletters**
Go hands-free with your news. Audioura converts **any article or newsletter into an audio stream**, reads a smart
summary, and lets you decide whether to hear the full story or move on. Filter by category (Business, Finance,
Politics), by date, or by **voice search** — even advanced searches like "find articles with X but without Y."
Paste an article and its audio edition is generated instantly; drop in a newsletter URL to get up to 10 articles.

**☕ Treats**
While you're on a tour or listening to the news, treat yourself — a coffee, lunch, or a souvenir from nearby spots,
shown right on your map.

**Voice-first, screen-free** (callout band):
Initiate with a triple-click of your headphones or a tap of the mic, then command: *"Play summary," "Skip,"
"Next article."* Compatible with most headphones. GPS gives you auto directions and POI summaries tuned to your
choices. Built so you never have to look at your phone.

*(Optional supporting points if room: increased engagement while multitasking, reduced screen fatigue,
multi-language with auto-translation.)*

## SECTION 3 — How to get it
Heading: **Get Audioura free**
Body: Available on iPhone and Android. Download, open, and start listening.
- **Apple App Store** — badge + link: `<APP_STORE_URL — placeholder, app not yet published>`
- **Google Play** — badge + link: `<GOOGLE_PLAY_URL — placeholder, app not yet published>`
Use the official store badge artwork. Until the apps are live, render the badges with a "Coming soon" ribbon or an
email-capture ("Notify me at launch") — confirm which with the owner.

## SECTION 4 — Pricing (Free vs Premium)
Heading: **Start free. Upgrade when you want more.**
Two-column comparison. **Prices are NOT finalized — leave the Premium price as a placeholder.**

| | **Free** | **Premium** *(coming soon)* |
|---|---|---|
| Audio tours | 1 per day (up to 30 stops) | Up to 10 per day (up to 50 stops) |
| Audio news / newsletters | 10 per week (up to 10 min each) | 50 per week (up to 30 min each) |
| Downloads | Unlimited | Unlimited |
| Voice control | ✓ | ✓ |
| Languages / auto-translation | ✓ | ✓ |
| Treats (local offers) | ✓ | ✓ |
| Price | **$0** | `$<PRICE>/mo — placeholder` |

Footnote: "Limits help us keep the free tier sustainable. Premium pricing and availability to be announced."

## SECTION 5 — Contact / Connect
Heading: **Let's connect**
- **Email:** info@audioura.com
- **Phone:** +1-617-744-9562
- **Social:** @letMeHear
- Optional: a simple contact form that emails info@audioura.com (or just a mailto link to keep it static).

## SECTION 6 — Footer
© Audioura LLC · [Privacy Policy](/privacy) · info@audioura.com · @letMeHear

---

## Build notes for the other chat
- **Format:** a single self-contained `index.html` (inline CSS, minimal/no JS) is ideal for easy hosting — but the
  builder may choose any simple static stack. Mobile-first, fast, accessible.
- **Reuse:** host `PRIVACY_POLICY.html` at `/privacy` (it's already written) so the store submission can point to
  `https://www.audioura.com/privacy`.
- **Placeholders to confirm with the owner before publishing:**
  - Store URLs (apps not yet published) — or use "coming soon" + notify-me.
  - Premium price and launch timing.
  - Logo, brand colors/fonts, and app screenshots.
  - Whether to include a contact form vs. plain mailto.
- **Accuracy guardrails:** use only the consumer copy above. Don't invent metrics, testimonials, partner names, or
  pricing. The free-tier limits above come from the live product (1 tour/day ≤30 stops; 10 news/week ≤10 min;
  unlimited downloads) and are accurate.
- **Contact consistency:** use `info@audioura.com` (one deck shows an older `info@AudioTours.AI` — do not use that).

## Sources
Audioura product decks (provided by owner, 2026-06-11): "AudioNews Platform / Newsletter Engagement,"
"User Workflow / Application Modes," and "AI-Powered Audio Tours."
