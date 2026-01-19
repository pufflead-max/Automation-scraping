"""Health check and monitoring endpoints."""

from typing import Dict, Any
from datetime import datetime, timedelta

from .database import get_db_manager
from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)


class HealthChecker:
    """Performs health checks on the scraping system."""
    
    def __init__(self):
        self.db = get_db_manager()
        self.settings = get_settings()
    
    def check_database(self) -> Dict[str, Any]:
        try:
            self.db.client.admin.command('ping')
            stats = self.db.db.command('dbStats')
            return {'status': 'healthy', 'connected': True, 'database': self.settings.mongo_db,
                   'collections': stats.get('collections', 0),
                   'data_size_mb': round(stats.get('dataSize', 0) / 1024 / 1024, 2)}
        except Exception as e:
            logger.error("database_health_check_failed", error=str(e))
            return {'status': 'unhealthy', 'connected': False, 'error': str(e)}
    
    def check_recent_jobs(self, hours: int = 24) -> Dict[str, Any]:
        try:
            jobs = self.db.find_many("scrape_jobs", {"started_at": {"$gte": datetime.utcnow() - timedelta(hours=hours)}})
            total = len(jobs)
            completed = sum(1 for job in jobs if job.get('status') == 'completed')
            failed = sum(1 for job in jobs if job.get('status') == 'failed')
            running = sum(1 for job in jobs if job.get('status') in ['started', 'running'])
            success_rate = (completed / total * 100) if total > 0 else 0
            
            return {'status': 'healthy' if success_rate >= 80 else 'degraded', 'time_window_hours': hours,
                   'total_jobs': total, 'completed': completed, 'failed': failed, 'running': running,
                   'success_rate_percent': round(success_rate, 2),
                   'total_leads_scraped': sum(job.get('items_saved', 0) for job in jobs)}
        except Exception as e:
            logger.error("job_health_check_failed", error=str(e))
            return {'status': 'unhealthy', 'error': str(e)}
    
    def check_data_freshness(self, hours: int = 24) -> Dict[str, Any]:
        try:
            recent_leads = self.db.find_many("leads", {"scraped_date": {"$gte": datetime.utcnow() - timedelta(hours=hours)}}, limit=1000)
            count = len(recent_leads)
            return {'status': 'healthy' if count > 0 else 'stale', 'time_window_hours': hours,
                   'recent_leads_count': count, 'data_is_fresh': count > 0}
        except Exception as e:
            logger.error("data_freshness_check_failed", error=str(e))
            return {'status': 'unhealthy', 'error': str(e)}
    
    def get_overall_health(self) -> Dict[str, Any]:
        db_health = self.check_database()
        jobs_health = self.check_recent_jobs(hours=24)
        data_health = self.check_data_freshness(hours=24)
        
        statuses = [db_health.get('status'), jobs_health.get('status'), data_health.get('status')]
        overall = 'unhealthy' if 'unhealthy' in statuses else 'degraded' if 'degraded' in statuses else 'healthy'
        
        return {'status': overall, 'timestamp': datetime.utcnow().isoformat(),
               'checks': {'database': db_health, 'recent_jobs': jobs_health, 'data_freshness': data_health}}


def get_system_metrics() -> Dict[str, Any]:
    db = get_db_manager()
    
    try:
        total_leads = db.db.leads.count_documents({})
        total_jobs = db.db.scrape_jobs.count_documents({})
        leads_by_source = {item['_id']: item['count'] for item in db.db.leads.aggregate([{"$group": {"_id": "$source", "count": {"$sum": 1}}}])}
        leads_by_category = {item['_id']: item['count'] for item in db.db.leads.aggregate([{"$group": {"_id": "$category", "count": {"$sum": 1}}}])}
        
        recent_jobs = list(db.db.scrape_jobs.find({"started_at": {"$gte": datetime.utcnow() - timedelta(days=7)}}))
        total_recent = len(recent_jobs)
        successful_recent = sum(1 for job in recent_jobs if job.get('status') == 'completed')
        success_rate = (successful_recent / total_recent * 100) if total_recent > 0 else 0
        
        return {'total_leads': total_leads, 'total_jobs': total_jobs, 'leads_by_source': leads_by_source,
               'leads_by_category': leads_by_category,
               'last_7_days': {'total_jobs': total_recent, 'successful_jobs': successful_recent,
                              'success_rate_percent': round(success_rate, 2)},
               'timestamp': datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("metrics_collection_failed", error=str(e))
        return {'error': str(e), 'timestamp': datetime.utcnow().isoformat()}
