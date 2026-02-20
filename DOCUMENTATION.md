# PUFF Comprehensive Technical Documentation v1.0

## 1. System Vision & Architecture
PUFF (Platform for Unified Filtering & Fetching) is an enterprise-grade lead generation engine. It focuses on the "In-Market" segment by crawling social graphs and marketplace listings for active buyer intent.

### 1.1 High-Level Architecture
The system follows a **Modular Micro-automation** pattern:
- **Data Acquisition Layer**: Platform-specific bots (Stage 1).
- **Intelligence Layer**: NLP-based intent detection and geographic enrichment (Stage 2).
- **Orchestration Layer**: Apache Airflow managing job state and concurrency (Stage 3).
- **Delivery Layer**: API-driven injection into GoHighLevel CRM (Stage 4).

### 1.2 The "Life of a Lead"
1. **Trigger**: Airflow's Scheduler triggers a task (e.g., `scrape_facebook_url_1`).
2. **Context Loading**: The task queries MongoDB `users` to find which client/vertical this URL belongs to.
3. **Execution**: A Selenium/Playwright worker launches (containerized), loads the "Owner Cookies" for that platform, and navigates to the URL.
4. **Filtering**: `BuyerIntentDetector` processes every post in real-time. It ignores "Ads", "Spam", and "Job seekers", keeping only "Service requests".
5. **Enrichment**: The system attempts to extract a Phone Number and City from the post text.
6. **Unique ID**: A `source_url` hash is generated to ensure this specific post is never saved twice.
7. **Sync**: If a lead is valid, it is pushed to GHL via the API, where GHL Workflows trigger automated SMS/WhatsApp replies.

---

## 2. Accounts, Access & Security
A centralized registry of the infrastructure powering PUFF.

### 2.1 Infrastructure Access
| Service | Access Type | Port | Endpoint/URL |
| :--- | :--- | :--- | :--- |
| **Server (VPS)** | SSH | 22 | `72.60.113.252` |
| **Airflow UI** | Web | 18081 | `http://72.60.113.252:18081` |
| **MongoDB** | DB Connection | 47018 | `mongodb://[user]:[pass]@72.60.113.252:47018/PUFF` |
| **GoHighLevel** | CRM API (V2) | 443 | `https://services.leadconnectorhq.com` |

### 2.2 System Credentials (Internal)
- **Airflow Superuser**: `Edno` / `Edno@Puff123`
- **MongoDB Root**: `automation-scraping` / `Mongodb_password12345`
- **MongoDB App User**: `scraper_admin` / `Mongodb_password12345`

### 2.3 Platform "Owner" Accounts
These are the accounts used to perform the actual scraping. They must remain active and require periodic cookie refreshes.
- **Facebook**: `rizzolli06@gmail.com` | Pass: `dino0088`
- **Nextdoor**: `nicknickbru@gmail.com` | Pass: `Mariaclara@20`

---

## 3. Database Schema Deep-Dive
PUFF uses MongoDB for its schema-less flexibility across different platforms.

### 3.1 Collection: `users`
This is the "Brain" of the system. Every client is a document here.
```json
{
  "user": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1...",
    "state": "Massachusetts",
    "city": "Boston",
    "verticals": ["Landscaping Services"]
  },
  "facebook": {
    "group_urls": ["https://fb.com/groups/bostonlandscaping"],
    "target_keywords": ["mowing", "landscaper", "yard"]
  }
}
```

### 3.2 Collection: `scrape_jobs`
Provides full observability into scraper health.
- `job_id`: UUID for log tracing.
- `status`: `started` -> `completed` OR `failed`.
- `items_found`: Total posts scanned.
- `items_saved`: Total leads meeting intent criteria.
- `error_type`: (e.g., `TimeoutException`) for automated repair.

### 3.3 Collection: `platform_final_data`
Stores the actual leads. Key fields include:
- `is_buyer_request`: Boolean (result of intent logic).
- `processed_text`: Cleaner version of the post for CRM display.
- `user_email`: Links the lead to the client who "owns" that territory.

---

## 4. Scraper Intelligence (The Logic)

### 4.1 Buyer Intent Detection (`BuyerIntentDetector`)
Instead of simple keyword matching, PUFF uses targeted linguistic patterns:
- **Positive Indicators**: "looking for", "recommendations for", "quote needed", "anyone do...", "searching for".
- **Negative Indicators (Blacklist)**: "hiring", "job available", "selling", "price: $", "I provide", "discount".
- **Logic**: Any post containing a Negative Indicator is immediately discarded, even if keywords match.

### 4.2 Handling Concurrency (`scraper_pool`)
To prevent platform bans, we use an Airflow Pool called `scraper_pool` set to a small slots value (e.g., 2-3). This ensures that even if 50 scraping tasks are scheduled, only 2 browse the web at a time, protecting our IP reputation.

---

## 5. GoHighLevel (GHL) Integration

### 5.1 Onboarding Sync
The `ghl_onboarding_sync_dag` runs hourly. It performs "Geo-Standardization":
- If a user types "MA" or "boston", the system matches it against the `geo_data` master list and saves `Massachusetts` and `Boston` (Standardized).
- This ensures the scraper only targets the correct region.

### 5.2 Lead Injection
Leads are pushed to GHL with custom tags:
- `automation_user`: Identifies leads from the system.
- `Lead Vertical`: (e.g., `Landscaping`).
- **Custom Objects**: Leads are saved as "Custom Object" records in GHL, allowing for detailed tracking without cluttering the main contact list's primary fields.

---

## 6. Technical Maintenance & FAQ

### How to update cookies manually?
1. Open the Airflow UI -> Admin -> Variables.
2. Update `facebook_cookies` or `nextdoor_cookies` with a fresh JSON array from a tool like "EditThisCookie".

### What happens if Facebook changes its UI?
The `FacebookScraper` uses a **Multi-Selector Fallback** system. It tries `[name="login"]`, then `#login`, then `button[type="submit"]`. This makes the system resilient to minor UI updates.

### How to scale to 1,000 users?
- Increase the number of slots in `scraper_pool`.
- Deploy additional "Scraper Workers" using Docker Swarm or Kubernetes.
- Implement a Proxy Rotation service (e.g., Bright Data or ScraperAPI).

---
**PUFF v1.0 | Stability & Documentation Project**
Prepared for: Internal Stakeholders & Future Transfers
Last Updated: Feb 20, 2026
