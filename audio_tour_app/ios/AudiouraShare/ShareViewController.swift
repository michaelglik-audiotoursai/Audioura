import UIKit
import UniformTypeIdentifiers

// [LOCAL-868 / D762] Share → Audioura (iOS).
//
// Takes the text another app shares (Musa.AI, Notes, ChatGPT, Safari…) and
// hands it to Audioura by opening  audioura://paste?text=<percent-encoded>.
// Audioura's DeepLinkService turns that URL into the "Paste a list of places"
// box, pre-filled. No App Group and no shared container: the text travels in the
// URL, so the only signing addition is this extension's own bundle id
// (com.audioura.audiotours.ShareExtension) under the existing team.
//
// The server caps pasted text at 8000 characters; we cut there so the URL stays
// well inside what iOS will open.
final class ShareViewController: UIViewController {
    private let maxChars = 8000

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        let label = UILabel()
        label.text = "Opening Audioura…"
        label.textColor = .secondaryLabel
        label.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        loadSharedText { [weak self] text in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let text = text, let url = self.pasteURL(for: text) {
                    self.open(url)
                }
                self.extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
            }
        }
    }

    /// First plain-text (or URL-as-text) attachment of the shared items.
    private func loadSharedText(_ done: @escaping (String?) -> Void) {
        let items = (extensionContext?.inputItems as? [NSExtensionItem]) ?? []
        var providers: [NSItemProvider] = []
        for item in items { providers.append(contentsOf: item.attachments ?? []) }

        if let p = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) }) {
            p.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { value, _ in
                if let s = value as? String { done(s) }
                else if let d = value as? Data { done(String(data: d, encoding: .utf8)) }
                else { done(nil) }
            }
            return
        }
        if let p = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.url.identifier) }) {
            p.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) { value, _ in
                done((value as? URL)?.absoluteString)
            }
            return
        }
        // Some apps put the text in the item's attributedContentText only.
        done(items.compactMap { $0.attributedContentText?.string }.first)
    }

    private func pasteURL(for text: String) -> URL? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        var c = URLComponents()
        c.scheme = "audioura"
        c.host = "paste"
        c.queryItems = [URLQueryItem(name: "text", value: String(trimmed.prefix(maxChars)))]
        return c.url
    }

    /// An extension cannot call UIApplication.shared; walk the responder chain
    /// to the hosting UIApplication and ask it to open the URL.
    private func open(_ url: URL) {
        var responder: UIResponder? = self
        while let r = responder {
            if let app = r as? UIApplication {
                app.open(url, options: [:], completionHandler: nil)
                return
            }
            responder = r.next
        }
    }
}
