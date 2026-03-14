import time
import schedule
from typing import Callable, Dict, Any

class JobScheduler:
    """
    Manages scheduled jobs for the application.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the scheduler with configuration.
        
        Args:
            config (Dict[str, Any]): Configuration dictionary containing 'scheduler' section.
        """
        self.config = config
        self.jobs = []
        
    def add_daily_job(self, job_func: Callable, time_str: str = None):
        """
        Add a daily job to run at a specific time.
        
        Args:
            job_func (Callable): The function to execute.
            time_str (str): The time to run the job (e.g., "08:00"). 
                            Defaults to config['scheduler']['time'].
        """
        if time_str is None:
            time_str = self.config.get('scheduler', {}).get('time', '08:00')
            
        print(f"Scheduling job for {time_str}")
        schedule.every().day.at(time_str).do(job_func)
        
    def start(self):
        """
        Start the scheduler loop. This is a blocking call.
        """
        print("Scheduler started. Press Ctrl+C to exit.")
        while True:
            schedule.run_pending()
            time.sleep(1)
