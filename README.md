# Automation Scraping System

A production-ready lead extraction system that scrapes service listings from Craigslist and Nextdoor, with automated workflows powered by Apache Airflow.

##  Project Overview

This system transforms experimental notebook-based scrapers into a robust, production-ready platform for extracting and managing service leads. It features:

- **Multi-platform scraping**: Craigslist and Nextdoor support
- **Automated workflows**: Airflow DAGs for scheduled scraping
- **Data quality**: Validation and deduplication
- **Structured logging**: JSON-based logging for monitoring
- **Error handling**: Automatic retries and graceful degradation
- **Database integration**: MongoDB for lead storage

##  Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Chrome/Chromium (installed automatically in Docker)
- MongoDB (provided via Docker Compose)
- PostgreSQL (provided via Docker Compose for Airflow)

##  Quick Start

### 1. Clone and Configure

```bash
cd /path/to/Automation-scraping

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

### 2. Start Services

```bash
# Build and start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f airflow-webserver
```

### 3. Access Airflow

Open your browser to: http://72.60.113.252:18081

- **Username**: Edno
- **Password**: Edno@Puff123

### 4. Run Your First Scrape

**Option A: Via Airflow UI**
1. Navigate to DAGs
2. Enable `craigslist_scraper`, `nextdoor_scraper`, or `facebook_scraper_dag`
3. Trigger manually or wait for scheduled run

**Option B: Via Command Line**
```bash
# Run Craigslist scraper
docker-compose exec airflow-webserver python /opt/airflow/scraper/src/main.py \
  --scraper craigslist \
  --target "https://boston.craigslist.org/search/aos" \
  --category automotive
```

##  Project Structure

```
Automation-scraping/
├── .env                          # Environment configuration
├── .env.example                  # Environment template
├── docker-compose.yml            # Docker services definition
├── IMPLEMENTATION_PLAN.md        # Detailed implementation roadmap
├── README.md                     # This file
│
├── scraper/                      # Scraper application
│   ├── src/
│   │   ├── scrapers/             # Scraper implementations
│   │   └── utils/                # Utility modules (url_loader, etc.)
│   ├── cookies/                  # Authentication cookies
│   └── urls/                     # URL Configuration files
│       ├── facebook_urls.txt
│       ├── craigslist_urls.txt
│       └── nextdoor_urls.txt
│
├── airflow/                      # Airflow configuration
│   ├── dags/                     # Scraper DAGs
│   └── logs/                     # Scraper & Airflow logs
```

##  URL Configuration & Dynamic Workers

The system uses a dynamic worker architecture where each URL defined in the configuration files is processed by a separate Airflow task in parallel.

### Configuration Files (`scraper/urls/`)

- **`facebook_urls.txt`**: List of Facebook group/page URLs.
- **`craigslist_urls.txt`**: List of Craigslist category URLs.
- **`nextdoor_urls.txt`**: List of Nextdoor neighborhood/city URLs.

### File Format
- **One URL per line**
- Lines starting with `#` are comments
- Empty lines are ignored

### How It Works
1. **Dynamic Loading**: DAGs read these files at runtime.
2. **Parallel Tasks**: For each URL, a dedicated task (e.g., `scrape_facebook_url_1`) is created.
3. **Scalability**: Add or remove URLs without modifying Python code.
4. **Fault Isolation**: If one URL fails, other tasks continue.

##  Admin Configuration (No-Code)

Admins can manage URLs and scraper settings directly from the **Airflow UI** without touching any code.

### Managing via Airflow Variables
1. Login to Airflow UI (e.g., `http://72.60.113.252:18081`).
2. Navigate to **Admin** -> **Variables**.
3. Create or Edit the following keys as needed:

#### 1. Facebook Configuration
| Variable Key | Description | Example Value |
| :--- | :--- | :--- |
| `facebook_target_url` | Comma-separated or newline-separated URLs | `https://fb.com/groups/1, https://fb.com/groups/2` |
| `facebook_post_limit` | Max posts to scrape per URL | `50` |
| `facebook_headless` | Browser visibility | `true` or `false` |
| `facebook_cookies` | JSON-format cookies string | `[{"name": "c_user", ...}]` |

#### 2. Nextdoor Configuration
| Variable Key | Description | Example Value |
| :--- | :--- | :--- |
| `nextdoor_target_url` | URLs to scrape | `https://nextdoor.com/news_feed/` |
| `nextdoor_max_pages` | How many pages to scroll | `10` |
| `nextdoor_cookies` | JSON-format cookies string | `[{"name": "nd_session", ...}]` |

#### 3. Craigslist Configuration
| Variable Key | Description | Example Value |
| :--- | :--- | :--- |
| `craigslist_target_url`| Specific category URLs | `https://boston.craigslist.org/search/sks` |
| `craigslist_max_pages` | Number of result pages to read | `5` |
| `craigslist_headless`  | Browser visibility | `true` |

### Configuration Priority
The system checks for settings in this specific order:
1. **Airflow Variables** (Highest Priority - Good for temporary/quick changes)
2. **MongoDB** (Stored in `scraper_config` collection)
3. **Local Files** (Stored in `scraper/urls/*.txt`)
4. **Static Defaults** (Built-in values in the code)

##  Configuration

### Environment Variables

Key configuration in `.env`:

```bash
# MongoDB
MONGO_URI=mongodb://scraper_admin:password@mongo:27017/PUFF?authSource=admin
MONGO_DB=PUFF

# ScraperAPI (for proxy)
SCRAPERAPI_KEY=your_key_here
SCRAPERAPI_PROXY=scraperapi.keep_headers=true:your_key@proxy-server.scraperapi.com:8001

# Scraper Settings
SCRAPER_TIMEOUT=30
SCRAPER_MAX_RETRIES=3
SCRAPER_RETRY_DELAY=5

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

##  Database Schema

### Leads Collection

```json
{
  "_id": "ObjectId",
  "source": "craigslist",
  "source_url": "https://...",
  "source_id": "1234567890",
  "title": "Service Title",
  "description": "Full description",
  "contact_name": "John Doe",
  "contact_email": "john@example.com",
  "contact_phone": "+15551234567",
  "location": "Boston, MA",
  "category": "automotive",
  "posted_date": "2026-01-15T00:00:00Z",
  "scraped_date": "2026-01-15T12:00:00Z",
  "images": ["url1", "url2"]
}
```

### Scrape Jobs Collection

```json
{
  "_id": "ObjectId",
  "job_id": "uuid",
  "scraper": "craigslist",
  "status": "completed",
  "target": "https://...",
  "category": "automotive",
  "started_at": "2026-01-15T12:00:00Z",
  "completed_at": "2026-01-15T12:05:00Z",
  "items_found": 100,
  "items_saved": 95,
  "items_failed": 5
}
```

##  Testing

### Run Smoke Tests

```bash
# Via Airflow
docker-compose exec airflow-webserver airflow dags test scrape_smoke_test

# Direct Python tests
docker-compose exec airflow-webserver python /opt/airflow/scraper/src/config.py
docker-compose exec airflow-webserver python /opt/airflow/scraper/src/database.py
```

### Test Individual Components

```bash
# Test configuration
python scraper/src/config.py

# Test database connection
python scraper/src/database.py

# Test models
python scraper/src/models.py

# Test validator
python scraper/src/processors/validator.py

# Test deduplicator
python scraper/src/processors/deduplicator.py
```

##  Monitoring

### View Logs

```bash
# Airflow webserver logs
docker-compose logs -f airflow-webserver

# Airflow scheduler logs
docker-compose logs -f airflow-scheduler

# MongoDB logs
docker-compose logs -f mongo

# All services
docker-compose logs -f
```

### Access MongoDB

```bash
# Connect to MongoDB
docker-compose exec mongo mongosh -u scraper_admin -p Mongodb_password12345 --authenticationDatabase admin

# Query leads
use PUFF
db.leads.find().limit(5)

# Check scrape jobs
db.scrape_jobs.find().sort({started_at: -1}).limit(10)
```

##  Security

### Production Checklist

- [ ] Change default MongoDB passwords in `.env`
- [ ] Use strong ScraperAPI key
- [ ] Enable Airflow authentication
- [ ] Use secrets management (e.g., Airflow Connections)
- [ ] Restrict network access to services
- [ ] Enable SSL/TLS for MongoDB
- [ ] Regular security updates for Docker images
- [ ] Implement rate limiting
- [ ] Monitor for suspicious activity

##  Troubleshooting

### Common Issues

**Issue**: Chrome/ChromeDriver not found
```bash
# Rebuild Airflow container
docker-compose build airflow-webserver
docker-compose up -d airflow-webserver
```

**Issue**: MongoDB connection failed
```bash
# Check MongoDB is running
docker-compose ps mongo

# Check credentials in .env
cat .env | grep MONGO

# Test connection
docker-compose exec mongo mongosh -u scraper_admin -p Mongodb_password12345 --authenticationDatabase admin
```

**Issue**: Import errors in Airflow
```bash
# Check PYTHONPATH
docker-compose exec airflow-webserver env | grep PYTHONPATH

# Reinstall dependencies
docker-compose exec airflow-webserver pip install -r /tmp/scraper-requirements.txt
```

##  Development

### Adding a New Scraper

1. Create scraper class in `scraper/src/scrapers/your_scraper.py`
2. Inherit from `BaseScraper`
3. Implement `scrape()` and `parse_item()` methods
4. Create corresponding Pydantic model in `models.py`
5. Add DAG in `airflow/dags/your_scraper_dag.py`
6. Update `main.py` to support new scraper

### Code Style

```bash
# Format code
black scraper/src/

# Sort imports
isort scraper/src/

# Type checking
mypy scraper/src/
```

##  Documentation

- [Implementation Plan](IMPLEMENTATION_PLAN.md) - Detailed roadmap
- [Airflow Documentation](https://airflow.apache.org/docs/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Selenium Documentation](https://www.selenium.dev/documentation/)

##  Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

##  License

Proprietary - All rights reserved

##  Support

For issues or questions:
1. Check the troubleshooting section
2. Review logs for error messages
3. Consult the implementation plan
4. Contact the development team

---

**Version**: 1.0.0
**Last Updated**: 2026-01-15
**Status**: Production Ready
