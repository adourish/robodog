"""
Schedule Email Workflow
Run the email automation workflow on a schedule
"""

import schedule
import time
import subprocess
import os
from datetime import datetime


def run_workflow():
    """Run the email automation workflow"""
    print(f"\n{'='*70}")
    print(f"Running Email Workflow - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    try:
        # Set environment variable
        env = os.environ.copy()
        env['GOOGLE_CLIENT_SECRET'] = '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'
        
        # Run workflow
        result = subprocess.run(
            ['python', 'email_automation_workflow.py'],
            env=env,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__)
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"\n✅ Workflow completed successfully at {datetime.now().strftime('%H:%M:%S')}")
        else:
            print(f"\n❌ Workflow failed with code {result.returncode}")
            print(result.stderr)
            
    except Exception as e:
        print(f"\n❌ Error running workflow: {e}")


def main():
    """Main scheduler"""
    print("="*70)
    print("EMAIL WORKFLOW SCHEDULER")
    print("="*70)
    print("\nSchedule Options:")
    print("1. Run once now")
    print("2. Run every hour")
    print("3. Run every 6 hours")
    print("4. Run daily at 9 AM")
    print("5. Run daily at 6 PM")
    print("6. Custom schedule")
    
    choice = input("\nSelect option (1-6): ").strip()
    
    if choice == '1':
        print("\n▶️  Running workflow once...")
        run_workflow()
        return
    
    elif choice == '2':
        schedule.every().hour.do(run_workflow)
        print("\n⏰ Scheduled to run every hour")
    
    elif choice == '3':
        schedule.every(6).hours.do(run_workflow)
        print("\n⏰ Scheduled to run every 6 hours")
    
    elif choice == '4':
        schedule.every().day.at("09:00").do(run_workflow)
        print("\n⏰ Scheduled to run daily at 9:00 AM")
    
    elif choice == '5':
        schedule.every().day.at("18:00").do(run_workflow)
        print("\n⏰ Scheduled to run daily at 6:00 PM")
    
    elif choice == '6':
        time_str = input("Enter time (HH:MM, 24-hour format): ").strip()
        schedule.every().day.at(time_str).do(run_workflow)
        print(f"\n⏰ Scheduled to run daily at {time_str}")
    
    else:
        print("\n❌ Invalid option")
        return
    
    # Run immediately on start
    print("\n▶️  Running initial workflow...")
    run_workflow()
    
    # Keep running
    print("\n⏰ Scheduler is running. Press Ctrl+C to stop.")
    print(f"   Next run: {schedule.next_run()}")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Scheduler stopped by user")


if __name__ == '__main__':
    main()
