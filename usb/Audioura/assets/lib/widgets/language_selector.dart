import 'package:flutter/material.dart';

class LanguageSelector extends StatefulWidget {
  final List<String> selectedLanguages;
  final Function(List<String>) onLanguagesChanged;
  final bool showEnglishNote;

  const LanguageSelector({
    Key? key,
    required this.selectedLanguages,
    required this.onLanguagesChanged,
    this.showEnglishNote = false,
  }) : super(key: key);

  @override
  State<LanguageSelector> createState() => _LanguageSelectorState();
}

class _LanguageSelectorState extends State<LanguageSelector> {
  static const Map<String, String> languages = {
    'en': 'English',
    'ru': 'Русский',
    'es': 'Español',
    'fr': 'Français',
    'de': 'Deutsch',
    'zh': '中文',
  };

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Languages:', style: TextStyle(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: languages.entries.map((entry) {
            final isSelected = widget.selectedLanguages.contains(entry.key);
            return FilterChip(
              label: Text(entry.value),
              selected: isSelected,
              onSelected: (selected) {
                List<String> newLanguages = List.from(widget.selectedLanguages);
                if (selected) {
                  newLanguages.add(entry.key);
                } else {
                  newLanguages.remove(entry.key);
                }
                widget.onLanguagesChanged(newLanguages);
              },
            );
          }).toList(),
        ),
        if (widget.showEnglishNote && !widget.selectedLanguages.contains('en'))
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Note: English will be generated as template for translations',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
      ],
    );
  }
}