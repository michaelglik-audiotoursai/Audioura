"""LOCAL-424: Call-site binding tests for verify_stop_claims.

These tests bind to the PRODUCTION call site — verify_stop_claims in
generate_tour_text.py — not the helper directly (story_verifier.py).

Binding proof (the way LEAD checks it):
  1. Keep story_verifier.py fully intact and importable.
  2. Neutralise ONLY the call site: set `_sv_result = None` or remove
     the call to verify_stop_claims in generate_tour_text.py.
  3. These tests go RED — proving they bind to the production code path.

The function verify_stop_claims:
  - Calls verify_story_candidate (from story_verifier)
  - Applies D369's vacuous-check: 0 claims extracted → forced FAIL
  - Returns the verification result that drives sentence-stripping

If you can neutralise verify_stop_claims without making these tests fail,
the binding is broken.
"""

import sys
import os
import ast

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestVerifyStopClaimsBindsToStoryVerifier:
    """Binding: verify_stop_claims calls verify_story_candidate from story_verifier.

    Goes RED if verify_stop_claims is neutralised (returns a hardcoded dict or
    stops calling the story_verifier module).
    """

    def test_claims_extracted_nonzero_on_real_story(self):
        """verify_stop_claims must extract real claims from story text.

        Goes RED if the call to verify_story_candidate (which calls extract_claims)
        is removed — claims_extracted would be 0 or the function would crash.
        """
        from generate_tour_text import verify_stop_claims

        story = (
            "Louis Broder, a visionary publisher known for his dedication to the "
            "livre d'artiste, commissioned Miro for this project. The lithographs "
            "were printed by the renowned Mourlot Freres."
        )
        snippets = [
            {'title': 'Broder publisher', 'snippet': 'Louis Broder published art books', 'url': 'http://x.com/1'},
        ]

        result = verify_stop_claims(story, snippets)

        assert result['claims_extracted'] >= 2, (
            f"BINDING FAILURE: verify_stop_claims returned claims_extracted="
            f"{result['claims_extracted']}. The call to verify_story_candidate "
            f"(which runs extract_claims) is not active."
        )

    def test_unsourced_claim_fails_verification(self):
        """A story with claims unsupported by any snippet must FAIL.

        Goes RED if verify_stop_claims is neutralised to always pass.
        """
        from generate_tour_text import verify_stop_claims

        story = (
            "Boris Fridman, a dedicated collector of artist books, generously "
            "donated this work to the Museum of Fine Arts, Boston."
        )
        # Provide NO relevant snippets — claims are unsourceable
        snippets = [
            {'title': 'Unrelated', 'snippet': 'The weather in Paris is mild.', 'url': 'http://x.com/2'},
        ]

        result = verify_stop_claims(story, snippets)

        assert not result['passed'], (
            f"BINDING FAILURE: story with unsourced claims passed verification. "
            f"verify_stop_claims is not running real verification. "
            f"Result: {result}"
        )
        assert result['claims_unsourced'] > 0, (
            f"BINDING FAILURE: no unsourced claims detected despite no matching snippets."
        )

    def test_vacuous_extraction_forces_fail_d369(self):
        """D369: if extract_claims returns 0 claims, verification is forced to FAIL.

        Goes RED if the vacuous-check inside verify_stop_claims is removed.
        This tests the D369 stop-gap (the production call site enforces it).
        """
        from generate_tour_text import verify_stop_claims

        # A story that triggers 0 claims from extraction (e.g. pure narrative
        # with no numbers, no proper nouns in descriptor position, no attributions)
        vacuous_story = "The light in the gallery is beautiful today."
        snippets = []

        result = verify_stop_claims(vacuous_story, snippets)

        assert not result['passed'], (
            f"BINDING FAILURE: vacuous extraction (0 claims) did not FAIL. "
            f"D369's vacuous-check is not active in verify_stop_claims."
        )
        assert any('VACUOUS' in r for r in result.get('rejection_reasons', [])), (
            f"BINDING FAILURE: rejection_reasons should contain 'VACUOUS' "
            f"when 0 claims are extracted. Got: {result.get('rejection_reasons')}"
        )

    def test_sourced_claim_passes(self):
        """A story whose claims ARE supported by snippets must PASS.

        Goes RED if verify_stop_claims always fails (negates the gate in
        either direction).
        """
        from generate_tour_text import verify_stop_claims

        story = (
            "The lithographs were printed by the renowned Mourlot Freres."
        )
        # Provide a snippet that supports the attribution claim
        snippets = [
            {
                'title': 'Mourlot printing house',
                'snippet': 'The lithographs were printed by Mourlot Frères, the famous Parisian printing house.',
                'url': 'http://source.com/mourlot',
            },
        ]

        result = verify_stop_claims(story, snippets)

        assert result['claims_extracted'] >= 1, (
            f"Expected at least 1 claim extracted. Got {result['claims_extracted']}."
        )
        assert result['claims_sourced'] >= 1, (
            f"Expected at least 1 sourced claim (snippet matches). "
            f"Got sourced={result['claims_sourced']}."
        )

    def test_evidence_includes_source_url(self):
        """Sourced claims must carry the source URL in evidence.

        Goes RED if verify_stop_claims returns a stub dict without real evidence.
        """
        from generate_tour_text import verify_stop_claims

        story = "The lithographs were printed by the renowned Mourlot Freres."
        snippets = [
            {
                'title': 'Mourlot Frères',
                'snippet': 'Printed by Mourlot Frères, lithographic printers since 1852.',
                'url': 'http://mourlot.example.com/about',
            },
        ]

        result = verify_stop_claims(story, snippets)

        assert result['evidence'], (
            f"BINDING FAILURE: no evidence returned. verify_stop_claims must return "
            f"evidence list with source URLs for sourced claims."
        )
        assert any('mourlot' in e.get('source_url', '').lower()
                  for e in result['evidence']), (
            f"Evidence must contain the Mourlot snippet URL. Got: {result['evidence']}"
        )


class TestCallSiteExistsInGenerateTourText:
    """AST-level binding: verify_stop_claims is actually CALLED inside
    generate_tour_text (not just defined and ignored).

    Catches the case where someone neutralises the call site by commenting it out
    or assigning `_sv_result = None`.
    """

    def test_verify_stop_claims_called_in_generate_tour_text(self):
        """The production function generate_tour_text must call verify_stop_claims.

        Uses AST analysis to confirm the call exists in the source — same technique
        as test_d370_story_pass_model.py.
        """
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text.py'
        )
        with open(source_path, 'r') as f:
            source = f.read()

        tree = ast.parse(source)

        # Find generate_tour_text function
        gen_func = None
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'generate_tour_text':
                gen_func = node
                break

        assert gen_func is not None, (
            "generate_tour_text function not found in generate_tour_text.py"
        )

        # Check that verify_stop_claims is called within generate_tour_text
        found_call = False
        for node in ast.walk(gen_func):
            if isinstance(node, ast.Call):
                # Direct call: verify_stop_claims(...)
                if isinstance(node.func, ast.Name) and node.func.id == 'verify_stop_claims':
                    found_call = True
                    break
                # Attribute call: self.verify_stop_claims(...) or module.verify_stop_claims(...)
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'verify_stop_claims':
                    found_call = True
                    break

        assert found_call, (
            "BINDING FAILURE: verify_stop_claims is not called inside "
            "generate_tour_text. The call site has been neutralised."
        )

    def test_result_assigned_to_sv_result(self):
        """The call to verify_stop_claims must assign its result to _sv_result.

        This ensures the result is actually USED (not called and discarded).
        """
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text.py'
        )
        with open(source_path, 'r') as f:
            source = f.read()

        tree = ast.parse(source)

        # Find generate_tour_text function
        gen_func = None
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'generate_tour_text':
                gen_func = node
                break

        # Check for assignment: _sv_result = verify_stop_claims(...)
        found_assignment = False
        for node in ast.walk(gen_func):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '_sv_result':
                        # Check right side is a call to verify_stop_claims
                        if isinstance(node.value, ast.Call):
                            if (isinstance(node.value.func, ast.Name) and
                                    node.value.func.id == 'verify_stop_claims'):
                                found_assignment = True
                                break

        assert found_assignment, (
            "BINDING FAILURE: _sv_result = verify_stop_claims(...) not found "
            "inside generate_tour_text. The call site result is not wired."
        )
