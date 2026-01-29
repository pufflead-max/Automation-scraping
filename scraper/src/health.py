"""Health check and monitoring endpoints  ."""

from typing import Dict, Any
from datetime import datetime, timedelta
from .database import get_db_manager
from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)

class HealthChecker:
    def __init__(self):
        self.db, self.settings = get_db_manager(), get_settings()
    
    def check_database(self) -> Dict[str, Any]:
        try:
            self.db.client.admin.command('ping')
            stats = self.db.db.command('dbStats')
            return {'status': 'healthy', 'connected': True, 'database': self.settings.mongo_db,
                    'collections': stats.get('collections', 0),
                    'size_mb': round(stats.get('dataSize', 0) / 1024 / 1024, 2)}
        except Exception as e:
            return {'status': 'unhealthy', 'connected': False, 'error': str(e)}
    
    def check_jobs(self, hours: int = 24) -> Dict[str, Any]:
        try:
            jobs = self.db.find_many("scrape_jobs", {"started_at": {"$gte": datetime.utcnow() - timedelta(hours=hours)}})
            total = len(jobs)
            comp = sum(1 for j in jobs if j.get('status') == 'completed')
            rate = (comp / total * 100) if total > 0 else 0
            return {'status': 'healthy' if rate >= 80 else 'degraded', 'total': total, 'completed': comp, 'rate': round(rate, 2)}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}
    
    def get_overall(self) -> Dict[str, Any]:
        db, jobs = self.check_database(), self.check_jobs()
        status = 'healthy' if all(s['status'] == 'healthy' for s in [db, jobs]) else 'unhealthy'
        return {'status': status, 'timestamp': datetime.utcnow().isoformat(), 'checks': {'db': db, 'jobs': jobs}}

def get_metrics() -> Dict[str, Any]:
    db = get_db_manager()
    try:
        counts = list(db.db.leads.aggregate([{"$group": {"_id": "$source", "count": {"$sum": 1}}}]))
        return {
            'total_leads': db.db.leads.count_documents({}),
            'by_source': {c['_id']: c['count'] for c in counts},
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {'error': str(e), 'timestamp': datetime.utcnow().isoformat()}
