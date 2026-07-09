"""
Supabase database service for job postings.
"""
import base64
import json
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta, timezone
from collections import Counter
import asyncio

from supabase import create_client, Client
from loguru import logger

from models.job_posting import JobPosting
from config.settings import settings


def _format_supabase_error(error: Exception) -> str:
    """Keep noisy API/HTML error payloads readable in logs."""
    error_text = str(error)
    if "<!DOCTYPE html>" in error_text or "<html" in error_text.lower():
        code = getattr(error, "code", None)
        message = getattr(error, "message", None)
        if code or message:
            return f"{code or 'unknown'}: {message or 'Supabase returned HTML error payload'}"
        return "Supabase returned an HTML error payload"
    return error_text[:500]


def _supabase_key_role(supabase_key: str) -> Optional[str]:
    """Best-effort extraction of the Supabase JWT role claim."""
    parts = supabase_key.split(".")
    if len(parts) != 3:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding).decode("utf-8")
        claims = json.loads(decoded)
    except Exception:
        return None

    role = claims.get("role")
    return role if isinstance(role, str) else None


class SupabaseService:
    """Service for interacting with Supabase database"""
    
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        key_role = _supabase_key_role(settings.SUPABASE_KEY)
        if key_role and key_role != "service_role":
            raise ValueError(
                "SUPABASE_KEY is a Supabase %s JWT, but this scraper needs a service_role key "
                "to write to swe_internship_postings without RLS failures." % key_role
            )
            
        self.client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )
        self.table = self.client.table(settings.TABLE_NAME)
        self._existing_hashes: Optional[Set[str]] = None
        self.logger = logger.bind(service="supabase")
    
    async def initialize(self):
        """Initialize the service and cache existing job hashes"""
        await self._load_existing_hashes()
    
    async def _load_existing_hashes(self):
        """Load all existing job hashes for faster duplicate checking"""
        try:
            response = await asyncio.to_thread(
                self.table.select("hash").execute
            )
            self._existing_hashes = {job["hash"] for job in response.data}
            self.logger.info(f"Loaded {len(self._existing_hashes)} existing job hashes")
        except Exception as e:
            self.logger.error(f"Error loading existing hashes: {_format_supabase_error(e)}")
            self._existing_hashes = set()
    
    async def insert_job(self, job: JobPosting) -> bool:
        """
        Insert a new job posting if it doesn't already exist.
        
        Args:
            job: JobPosting to insert
            
        Returns:
            True if job was inserted (new), False if it already existed
        """
        # Quick check using cached hashes
        if self._existing_hashes and job.hash in self._existing_hashes:
            self.logger.debug(f"Job already exists (cached): {job.company} - {job.title}")
            return False
        
        try:
            # Insert the job
            record = job.to_supabase_record()
            response = await asyncio.to_thread(
                self.table.insert(record).execute
            )
            
            if response.data:
                self.logger.success(f"✅ Inserted new job: {job.company} - {job.title}")
                if self._existing_hashes:
                    self._existing_hashes.add(job.hash)
                return True
            else:
                self.logger.warning(f"Failed to insert job: {job.company} - {job.title}")
                return False
                
        except Exception as e:
            error_str = str(e)
            
            # Check if it's a duplicate key error (23505 is PostgreSQL duplicate key error code)
            if '23505' in error_str or 'duplicate key' in error_str.lower():
                # This is expected - job already exists
                self.logger.debug(f"🔄 Duplicate job (skipped): {job.company} - {job.title}")
                if self._existing_hashes:
                    self._existing_hashes.add(job.hash)
                return False
            else:
                # Unexpected error - log as error
                self.logger.error(
                    f"❌ Unexpected error inserting job {job.company} - {job.title}: "
                    f"{_format_supabase_error(e)}"
                )
                return False
    
    async def insert_multiple_jobs(self, jobs: List[JobPosting]) -> List[JobPosting]:
        """
        Insert multiple jobs and return the ones that were new.
        
        Args:
            jobs: List of JobPostings to insert
            
        Returns:
            List of JobPostings that were successfully inserted (new jobs)
        """
        new_jobs = []
        
        # Process in batches for efficiency
        batch_size = 10
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            
            # Check which jobs are new
            tasks = [self.insert_job(job) for job in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for job, result in zip(batch, results):
                if isinstance(result, bool) and result:
                    new_jobs.append(job)
                elif isinstance(result, Exception):
                    self.logger.error(
                        f"Error inserting job {job.company} - {job.title}: "
                        f"{_format_supabase_error(result)}"
                    )
        
        return new_jobs
    
    async def job_exists(self, hash_value: str) -> bool:
        """Check if a job with the given hash already exists"""
        try:
            response = await asyncio.to_thread(
                self.table.select("id").eq("hash", hash_value).limit(1).execute
            )
            return bool(response.data)
        except Exception as e:
            self.logger.error(f"Error checking job existence: {_format_supabase_error(e)}")
            return False
    
    async def get_recent_jobs(self, days: int = 7) -> List[Dict]:
        """Get jobs posted in the last N days"""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            response = await asyncio.to_thread(
                self.table.select("*")
                .gte("scraped_at", cutoff_date)
                .order("scraped_at", desc=True)
                .execute
            )
            return response.data
        except Exception as e:
            self.logger.error(f"Error fetching recent jobs: {_format_supabase_error(e)}")
            return []
    
    async def get_job_stats(self) -> Dict:
        """Get statistics about jobs in the database"""
        try:
            # Get all jobs
            response = await asyncio.to_thread(
                self.table.select("company", "scraped_at").execute
            )
            jobs = response.data
            
            if not jobs:
                return {
                    "total_jobs": 0,
                    "companies": {},
                    "recent_jobs": 0
                }
            
            # Calculate stats
            total_jobs = len(jobs)
            companies = Counter(job['company'] for job in jobs)
            
            # Recent jobs (last 7 days)
            now = datetime.now(timezone.utc)
            recent_cutoff = now - timedelta(days=7)
            recent_jobs = [
                job for job in jobs 
                if self._parse_datetime(job.get('scraped_at')) and 
                self._parse_datetime(job['scraped_at']) > recent_cutoff
            ]
            
            return {
                "total_jobs": total_jobs,
                "companies": dict(companies.most_common()),
                "recent_jobs": len(recent_jobs)
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating job stats: {_format_supabase_error(e)}")
            return {
                "total_jobs": 0,
                "companies": {},
                "recent_jobs": 0
            }
    
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string to timezone-aware datetime"""
        if not dt_str:
            return None
        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
    
    async def cleanup_old_jobs(self, days_to_keep: int = 30):
        """Remove jobs older than specified days"""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()
            response = await asyncio.to_thread(
                self.table.delete().lt("scraped_at", cutoff_date).execute
            )
            count = len(response.data) if response.data else 0
            self.logger.info(f"Cleaned up {count} old jobs")
            
            # Reload hashes after cleanup
            await self._load_existing_hashes()
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old jobs: {_format_supabase_error(e)}")
