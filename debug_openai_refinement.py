#!/usr/bin/env python3
"""
Debug script for OpenAI refinement in newsletter processing
"""
import os
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

def refine_articles_with_openai(candidate_urls):
    """Use OpenAI to refine article detection for ambiguous URLs"""
    if not candidate_urls or len(candidate_urls) == 0:
        return []
    
    try:
        # Prepare URLs for OpenAI analysis
        url_list = "\\n".join([f"{i+1}. {url}" for i, url in enumerate(candidate_urls)])
        
        prompt = f"""Analyze these URLs and identify which ones are likely to be individual news articles (not section pages, category pages, or navigation pages).

URLs to analyze:
{url_list}

Return only the numbers of URLs that are likely individual articles, separated by commas. For example: 1,3,5

Look for:
- Descriptive slugs with multiple words
- Article IDs or dates
- Specific story titles in the URL

Avoid:
- Section roots (/news/, /sports/)
- Category pages
- Navigation pages
- Search results"""
        
        print(f"PROMPT SENT TO OPENAI:")
        print(prompt)
        print(f"\\n" + "="*50 + "\\n")
        
        # Simple OpenAI API call (requires OPENAI_API_KEY environment variable)
        openai_response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {os.getenv("OPENAI_API_KEY")}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-3.5-turbo',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 100,
                'temperature': 0.1
            },
            timeout=10
        )
        
        if openai_response.status_code == 200:
            result = openai_response.json()
            content = result['choices'][0]['message']['content'].strip()
            
            print(f"OPENAI RESPONSE:")
            print(content)
            print(f"\\n" + "="*50 + "\\n")
            
            # Parse the response (expecting comma-separated numbers)
            try:
                selected_indices = [int(x.strip()) - 1 for x in content.split(',') if x.strip().isdigit()]
                refined_urls = [candidate_urls[i] for i in selected_indices if 0 <= i < len(candidate_urls)]
                
                print(f"SELECTED ARTICLES ({len(refined_urls)} out of {len(candidate_urls)}):")
                for i, url in enumerate(refined_urls, 1):
                    print(f"{i}. {url}")
                
                logging.info(f"OpenAI refined {len(candidate_urls)} URLs to {len(refined_urls)} articles")
                return refined_urls
            except Exception as e:
                print(f"ERROR PARSING OPENAI RESPONSE: {e}")
                logging.warning(f"Could not parse OpenAI response: {content}")
                return candidate_urls[:5]  # Fallback: take first 5
        else:
            print(f"OPENAI API ERROR: {openai_response.status_code}")
            print(openai_response.text)
            logging.warning(f"OpenAI API error: {openai_response.status_code}")
            return candidate_urls[:5]  # Fallback
            
    except Exception as e:
        print(f"OPENAI REFINEMENT ERROR: {e}")
        logging.error(f"OpenAI refinement error: {e}")
        return candidate_urls[:5]  # Fallback

def test_openai_refinement():
    """Test OpenAI refinement with the candidate URLs from API Security newsletter"""
    candidate_urls = [
        "https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/#content",
        "https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/",
        "https://apisecurity.io/owasp-api-security-top-10/",
        "https://apisecurity.io/owasp-api-security-top-10/owasp-api-security-top-10-2019/",
        "https://apisecurity.io/owasp-api-security-top-10/owasp-api-security-top-10-project/",
        "https://www.facebook.com/sharer/sharer.php?u=https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/",
        "https://twitter.com/share?url=Check out this article:%20Issue 279: Tax records leak, Hacked service robots, Frostbyte at US stores, Layer 7 API attacks%20-%20https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/",
        "https://www.linkedin.com/shareArticle?mini=true&url=https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/&title=Issue 279: Tax records leak, Hacked service robots, Frostbyte at US stores, Layer 7 API attacks&summary=Newsletter=&source=ApiSecurity.io",
        "https://aseem-shrey.medium.com/manipulating-indias-stock-market-the-gst-portal-data-leak-b5437c817071",
        "https://bobdahacker.com/blog/hacked-biggest-chinese-robot-company",
        "https://cybersecuritynews.com/hashicorp-vault-vulnerability/",
        "https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/",
        "https://www.rapid7.com/blog/post/securden-unified-pam-multiple-critical-vulnerabilities-fixed/",
        "https://cybersecuritynews.com/esphome-web-server-authentication-bypass",
        "https://apisecurity.io/issue-278-owasp-api-bugs-at-intel-teaforher-mcdonalds-optus-breach-fallout-apis-for-ai-agents/",
        "https://apisecurity.io/issue-280-solar-device-ato-attacks-smart-tvs-dumb-apis-password-reset-api-bugs-2025-developer-survey/",
        "https://apisecurity.io/issue-277-hacking-wafs-ai-benefits-and-risks-ai-ready-with-openapi-developers-exposed/",
        "https://apisecurity.io/issue-276-api-discovery-hype-bola-at-mcdonalds-cisco-apis-exploited-input-validation-best-practices/",
        "https://apisecurity.io/issue-275-api-hackers-strike-gold-malicious-api-drift-at-coinmarketcap-survey-reveals-major-api-security-gaps/",
        "https://apisecurity.io/issue-274-authorization-nightmares-api-security-case-studies-23andme-fined-2-3m-oauth-for-cloud-native-apis/"
    ]
    
    print("=== TESTING OPENAI REFINEMENT ===\\n")
    print(f"Testing with {len(candidate_urls)} candidate URLs\\n")
    
    refined_urls = refine_articles_with_openai(candidate_urls)
    
    print(f"\\nFINAL RESULT: {len(refined_urls)} articles selected")

if __name__ == '__main__':
    test_openai_refinement()