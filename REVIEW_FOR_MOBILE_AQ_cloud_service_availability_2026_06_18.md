# FOR MOBILE AMAZON-Q — Cloud Service Availability (2026-06-18)

**Context:** Mobile is migrating hardcoded local URLs to the cloud gateway. Here's what's available and what's NOT.

---

## Services WITH cloud gateway routes (use these in cloud mode)

| Feature | Cloud path | Method | Auth |
|---------|-----------|--------|------|
| Tour generation | `POST /generate-complete-tour` | POST | API key |
| Tour status | `GET /status/<job_id>` | GET | Public |
| Tour download | `GET /download/<job_id>` | GET | Public |
| Translation | `POST /translate-with-audio` | POST | API key |
| News generation | `POST /generate-news` | POST | API key |
| News status | `GET /news-status/<article_id>` | GET | Public |
| News download | `GET /news-download/<article_id>` | GET | Public |
| Newsletter process | `POST /process_newsletter` | POST | API key |
| Newsletter list | `GET /newsletters_v2` | GET | Public |
| Articles by newsletter | `POST /get_articles_by_newsletter_id` | POST | Public |
| Submit credentials | `POST /submit_credentials` | POST | API key |
| Consolidation status | `GET /get_user_consolidation_status/<device_id>` | GET | Public |
| Delete account | `DELETE /delete-account/<secret_id>` | DELETE | API key |
| Map/tours near | `GET /tours-near/<lat>/<lng>` | GET | Public |
| Download tour | `GET /download-tour/<tour_id>` | GET | Public |
| Search tours | `GET|POST /search-tours` | GET/POST | Public |

---

## Services NOT on cloud — gate these features off in cloud mode

| Local port | Service | Status | Action for Mobile |
|-----------|---------|--------|-------------------|
| **5008** | Voice control (OpenAI commands) | ❌ NOT deployed to Cloud Run, NOT in gateway | **Gate off** in cloud mode |
| **5007** | Treats (local offers) | ❌ NOT deployed to Cloud Run, NOT in gateway | **Gate off** in cloud mode |
| **5022** | Tour editing | ❌ NOT deployed to Cloud Run, NOT in gateway | **Gate off** in cloud mode |

These services exist only in the local Docker Compose environment. They have no Cloud Run deployment and no gateway route. Calling them in cloud mode will timeout or 404.

---

## Recommendation

For the Beta/v1 launch, the app should:
1. Use cloud gateway paths for all listed services above
2. **Disable** voice control, treats, and tour editing features when in cloud mode (show a "coming soon" or hide the UI)
3. These can be deployed to Cloud Run and added to the gateway in Release 2 if needed
