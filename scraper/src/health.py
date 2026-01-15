"""
Health check and monitoring endpoints.
Can be used by monitoring systems to check scraper health.
"""

from typing import Dict, Any
from datetime import datetime, timedelta

from .database import get_db_manager
from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)


class HealthChecker:
    """
    Performs health checks on the scraping system.
    """
    
    def __init__(self):
        """Initialize health checker."""
        self.db = get_db_manager()
        self.settings = get_settings()
    
    def check_database(self) -> Dict[str, Any]:
        """
        Check database connectivity and health.
        
        Returns:
            Dict: Health check results
        """
        try:
            # Try to ping database
            self.db.client.admin.command('ping')
            
            # Get database stats
            stats = self.db.db.command('dbStats')
            
            return {
                'status': 'healthy',
                'connected': True,
                'database': self.settings.mongo_db,
                'collections': stats.get('collections', 0),
                'data_size_mb': round(stats.get('dataSize', 0) / 1024 / 1024, 2),
            }
        except Exception as e:
            logger.error("database_health_check_failed", error=str(e))
            return {
                'status': 'unhealthy',
                'connected': False,
                'error': str(e)
            }
    
    def check_recent_jobs(self, hours: int = 24) -> Dict[str, Any]:
        """
        Check recent scraping jobs.
        
        Args:
            hours: How many hours back to check
        
        Returns:
            Dict: Job statistics
        """
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            jobs = self.db.find_many(
                "scrape_jobs",
                {"started_at": {"$gte": cutoff}}
            )
            
            total = len(jobs)
            completed = sum(1 for job in jobs if job.get('status') == 'completed')
            failed = sum(1 for job in jobs if job.get('status') == 'failed')
            running = sum(1 for job in jobs if job.get('status') in ['started', 'running'])
            
            total_leads = sum(job.get('items_saved', 0) for job in jobs)
            
            success_rate = (completed / total * 100) if total > 0 else 0
            
            return {
                'status': 'healthy' if success_rate >= 80 else 'degraded',
                'time_window_hours': hours,
                'total_jobs': total,
                'completed': completed,
                'failed': failed,
                'running': running,
                'success_rate_percent': round(success_rate, 2),
                'total_leads_scraped': total_leads,
            }
        except Exception as e:
            logger.error("job_health_check_failed", error=str(e))
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    def check_data_freshness(self, hours: int = 24) -> Dict[str, Any]:
        """
        Check if we're getting fresh data.
        
        Args:
            hours: How many hours back to check
        
        Returns:
            Dict: Data freshness statistics
        """
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            recent_leads = self.db.find_many(
                "leads",
                {"scraped_date": {"$gte": cutoff}},
                limit=1000
            )
            
            count = len(recent_leads)
            is_fresh = count > 0
            
            return {
                'status': 'healthy' if is_fresh else 'stale',
                'time_window_hours': hours,
                'recent_leads_count': count,
                'data_is_fresh': is_fresh,
            }
        except Exception as e:
            logger.error("data_freshness_check_failed", error=str(e))
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    def get_overall_health(self) -> Dict[str, Any]:
        """
        Get overall system health.
        
        Returns:
            Dict: Complete health check results
        """
        database_health = self.check_database()
        jobs_health = self.check_recent_jobs(hours=24)
        data_health = self.check_data_freshness(hours=24)
        
        # Determine overall status
        statuses = [
            database_health.get('status'),
            jobs_health.get('status'),
            data_health.get('status')
        ]
        
        if 'unhealthy' in statuses:
            overall_status = 'unhealthy'
        elif 'degraded' in statuses:
            overall_status = 'degraded'
        else:
            overall_status = 'healthy'
        
        return {
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {
                'database': database_health,
                'recent_jobs': jobs_health,
                'data_freshness': data_health,
            }
        }


def get_system_metrics() -> Dict[str, Any]:
    """
    Get system-wide metrics.
    
    Returns:
        Dict: System metrics
    """
    db = get_db_manager()
    
    try:
        # Total counts
        total_leads = db.db.leads.count_documents({})
        total_jobs = db.db.scrape_jobs.count_documents({})
        
        # Leads by source
        leads_by_source = list(db.db.leads.aggregate([
            {"$group": {"_id": "$source", "count": {"$sum": 1}}}
        ]))
        
        # Leads by category
        leads_by_category = list(db.db.leads.aggregate([
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ]))
        
        # Recent job success rate
        recent_jobs = list(db.db.scrape_jobs.find(
            {"started_at": {"$gte": datetime.utcnow() - timedelta(days=7)}}
        ))
        
        total_recent = len(recent_jobs)
        successful_recent = sum(1 for job in recent_jobs if job.get('status') == 'completed')
        success_rate = (successful_recent / total_recent * 100) if total_recent > 0 else 0
        
        return {
            'total_leads': total_leads,
            'total_jobs': total_jobs,
            'leads_by_source': {item['_id']: item['count'] for item in leads_by_source},
            'leads_by_category': {item['_id']: item['count'] for item in leads_by_category},
            'last_7_days': {
                'total_jobs': total_recent,
                'successful_jobs': successful_recent,
                'success_rate_percent': round(success_rate, 2)
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("metrics_collection_failed", error=str(e))
        return {
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


if __name__ == "__main__":
    # Test health checks
    print("Testing health checker...")
    
    checker = HealthChecker()
    
    print("\n1. Database Health:")
    db_health = checker.check_database()
    print(f"   Status: {db_health.get('status')}")
    print(f"   Connected: {db_health.get('connected')}")
    
    print("\n2. Recent Jobs (24h):")
    jobs_health = checker.check_recent_jobs(hours=24)
    print(f"   Status: {jobs_health.get('status')}")
    print(f"   Total Jobs: {jobs_health.get('total_jobs')}")
    print(f"   Success Rate: {jobs_health.get('success_rate_percent')}%")
    
    print("\n3. Data Freshness:")
    data_health = checker.check_data_freshness(hours=24)
    print(f"   Status: {data_health.get('status')}")
    print(f"   Recent Leads: {data_health.get('recent_leads_count')}")
    
    print("\n4. Overall Health:")
    overall = checker.get_overall_health()
    print(f"   Status: {overall.get('status')}")
    
    print("\n5. System Metrics:")
    metrics = get_system_metrics()
    print(f"   Total Leads: {metrics.get('total_leads')}")
    print(f"   Total Jobs: {metrics.get('total_jobs')}")
    
    print("\n✓ Health check tests complete!")
